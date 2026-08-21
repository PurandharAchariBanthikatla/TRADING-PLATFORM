"""Wallet operations.

Every function here that moves value calls ledger_client.post_transaction()
-- there is no code path in this module that adjusts a balance without
going through ledger-service's double-entry engine. What lives here is
purely: idempotency bookkeeping in wallet-service's own tables, withdrawal
limit checks, and the lock/release/settle state machine for withdrawals.

Idempotency pattern used throughout: check wallet-service's local table for
an existing row with the given `reference` first (fast path for retries).
If a race means two callers both pass that check, the local unique
constraint on `reference` still prevents a duplicate row; the loser catches
the IntegrityError, rolls back, and re-fetches the winner's row instead of
erroring. The ledger call itself is *also* idempotent on the same
reference, so even a partial retry (ledger call succeeded, local insert
didn't) is safe to redo from the top.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.ledger_client import LedgerClient
from app.core.config import settings
from app.models.deposit import Deposit, DepositStatus
from app.models.transfer import InternalTransfer, TransferStatus
from app.models.wallet import Wallet
from app.models.withdrawal import WithdrawalRequest, WithdrawalStatus

USER_AVAILABLE = "user_available"
USER_LOCKED = "user_locked"
USER_PENDING = "user_pending"
SYSTEM_RESERVE = "system_reserve"


class WalletError(Exception):
    pass


class WithdrawalLimitExceededError(WalletError):
    pass


class InvalidWithdrawalStateError(WalletError):
    """Raised when approve/reject is attempted on a withdrawal that isn't
    PENDING_APPROVAL -- e.g. double-approval, or approving an already
    rejected request.
    """


async def get_or_create_wallet(db: AsyncSession, ledger: LedgerClient, *, user_id: str, asset: str) -> Wallet:
    existing = (
        await db.execute(select(Wallet).where(Wallet.user_id == user_id, Wallet.asset == asset))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    available = await ledger.get_or_create_account(
        owner_type="user", owner_id=user_id, asset=asset, account_type=USER_AVAILABLE
    )
    locked = await ledger.get_or_create_account(
        owner_type="user", owner_id=user_id, asset=asset, account_type=USER_LOCKED
    )
    pending = await ledger.get_or_create_account(
        owner_type="user", owner_id=user_id, asset=asset, account_type=USER_PENDING
    )

    wallet = Wallet(
        user_id=user_id,
        asset=asset,
        ledger_available_account_id=available.id,
        ledger_locked_account_id=locked.id,
        ledger_pending_account_id=pending.id,
    )
    db.add(wallet)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a race with a concurrent get_or_create_wallet() call for the
        # same (user_id, asset) -- the ledger accounts above are themselves
        # idempotent gets, so no leaked state; just return the winner's row.
        await db.rollback()
        existing = (
            await db.execute(select(Wallet).where(Wallet.user_id == user_id, Wallet.asset == asset))
        ).scalar_one()
        return existing

    await db.refresh(wallet)
    return wallet


@dataclass(frozen=True)
class WalletBalances:
    asset: str
    available: Decimal
    locked: Decimal
    pending: Decimal

    @property
    def total(self) -> Decimal:
        return self.available + self.locked + self.pending


async def get_wallet_balances(ledger: LedgerClient, wallet: Wallet) -> WalletBalances:
    available = await ledger.get_account(str(wallet.ledger_available_account_id))
    locked = await ledger.get_account(str(wallet.ledger_locked_account_id))
    pending = await ledger.get_account(str(wallet.ledger_pending_account_id))
    return WalletBalances(
        asset=wallet.asset, available=available.balance, locked=locked.balance, pending=pending.balance
    )


async def _reserve_account_id(ledger: LedgerClient, asset: str) -> str:
    reserve = await ledger.get_or_create_account(
        owner_type="system", owner_id=None, asset=asset, account_type=SYSTEM_RESERVE
    )
    return reserve.id


async def deposit(
    db: AsyncSession,
    ledger: LedgerClient,
    *,
    wallet: Wallet,
    amount: Decimal,
    reference: str,
    metadata: dict | None = None,
) -> tuple[Deposit, bool]:
    """Paper deposit: credits wallet.ledger_available_account_id, debits
    the asset's SYSTEM_RESERVE account. Settles synchronously (paper funds
    have no confirmations to wait on) -- see DepositStatus docstring.
    """
    existing = (await db.execute(select(Deposit).where(Deposit.reference == reference))).scalar_one_or_none()
    if existing is not None:
        return existing, False

    reserve_id = await _reserve_account_id(ledger, wallet.asset)

    txn = await ledger.post_transaction(
        reference=reference,
        source_type="deposit",
        entries=[
            {"account_id": reserve_id, "direction": "debit", "asset": wallet.asset, "amount": str(amount)},
            {
                "account_id": str(wallet.ledger_available_account_id),
                "direction": "credit",
                "asset": wallet.asset,
                "amount": str(amount),
            },
        ],
        description=f"Paper deposit of {amount} {wallet.asset}",
        metadata={"wallet_id": str(wallet.id), **(metadata or {})},
    )

    record = Deposit(
        wallet_id=wallet.id,
        reference=reference,
        asset=wallet.asset,
        amount=amount,
        status=DepositStatus.CONFIRMED,
        ledger_transaction_reference=txn.reference,
        deposit_metadata=metadata or {},
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (await db.execute(select(Deposit).where(Deposit.reference == reference))).scalar_one()
        return existing, False

    await db.refresh(record)
    return record, True


async def _withdrawn_today_total(db: AsyncSession, wallet_id: str) -> Decimal:
    start_of_day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(WithdrawalRequest).where(
            WithdrawalRequest.wallet_id == wallet_id,
            WithdrawalRequest.status.in_(
                [WithdrawalStatus.PENDING_APPROVAL, WithdrawalStatus.APPROVED, WithdrawalStatus.COMPLETED]
            ),
            WithdrawalRequest.created_at >= start_of_day,
        )
    )
    rows = result.scalars().all()
    return sum((Decimal(r.amount) for r in rows), Decimal(0))


async def request_withdrawal(
    db: AsyncSession,
    ledger: LedgerClient,
    *,
    wallet: Wallet,
    amount: Decimal,
    destination: str,
    reference: str,
    metadata: dict | None = None,
) -> tuple[WithdrawalRequest, bool]:
    """Locks funds (available -> locked) and creates a request awaiting
    admin approval. The lock happens immediately so the funds can't be
    spent elsewhere while the request is pending -- approval only ever
    needs to move locked -> system reserve or locked -> available, never
    touches available directly.
    """
    existing = (
        await db.execute(select(WithdrawalRequest).where(WithdrawalRequest.reference == reference))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    if amount > settings.MAX_WITHDRAWAL_PER_TRANSACTION:
        raise WithdrawalLimitExceededError(
            f"amount {amount} exceeds max per-transaction limit {settings.MAX_WITHDRAWAL_PER_TRANSACTION}"
        )

    already_withdrawn = await _withdrawn_today_total(db, str(wallet.id))
    if already_withdrawn + amount > settings.MAX_WITHDRAWAL_PER_DAY:
        raise WithdrawalLimitExceededError(
            f"amount {amount} would exceed daily withdrawal limit "
            f"{settings.MAX_WITHDRAWAL_PER_DAY} (already withdrawn today: {already_withdrawn})"
        )

    lock_reference = f"{reference}:lock"
    # LedgerInsufficientBalanceError propagates to the caller uncaught --
    # deliberately not turned into a domain-specific wallet exception here,
    # since ledger-service is the sole authority on "does this account
    # actually have enough", and there is nothing wallet-service could add
    # by re-wrapping that determination.
    await ledger.post_transaction(
        reference=lock_reference,
        source_type="internal_transfer",
        entries=[
            {
                "account_id": str(wallet.ledger_available_account_id),
                "direction": "debit",
                "asset": wallet.asset,
                "amount": str(amount),
            },
            {
                "account_id": str(wallet.ledger_locked_account_id),
                "direction": "credit",
                "asset": wallet.asset,
                "amount": str(amount),
            },
        ],
        description=f"Lock {amount} {wallet.asset} pending withdrawal approval",
        metadata={"wallet_id": str(wallet.id), "withdrawal_reference": reference},
    )

    record = WithdrawalRequest(
        wallet_id=wallet.id,
        reference=reference,
        asset=wallet.asset,
        amount=amount,
        destination=destination,
        status=WithdrawalStatus.PENDING_APPROVAL,
        lock_ledger_reference=lock_reference,
        withdrawal_metadata=metadata or {},
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(select(WithdrawalRequest).where(WithdrawalRequest.reference == reference))
        ).scalar_one()
        return existing, False

    await db.refresh(record)
    return record, True


async def approve_withdrawal(
    db: AsyncSession, ledger: LedgerClient, *, withdrawal: WithdrawalRequest, reviewer_user_id: str
) -> WithdrawalRequest:
    if withdrawal.status != WithdrawalStatus.PENDING_APPROVAL:
        raise InvalidWithdrawalStateError(
            f"withdrawal {withdrawal.id} is {withdrawal.status.value}, not pending_approval"
        )

    wallet = (await db.execute(select(Wallet).where(Wallet.id == withdrawal.wallet_id))).scalar_one()
    reserve_id = await _reserve_account_id(ledger, withdrawal.asset)
    settlement_reference = f"{withdrawal.reference}:settle"

    await ledger.post_transaction(
        reference=settlement_reference,
        source_type="withdrawal",
        entries=[
            {
                "account_id": str(wallet.ledger_locked_account_id),
                "direction": "debit",
                "asset": withdrawal.asset,
                "amount": str(Decimal(withdrawal.amount)),
            },
            {
                "account_id": reserve_id,
                "direction": "credit",
                "asset": withdrawal.asset,
                "amount": str(Decimal(withdrawal.amount)),
            },
        ],
        description=f"Withdrawal of {withdrawal.amount} {withdrawal.asset} to {withdrawal.destination}",
        metadata={"wallet_id": str(wallet.id), "withdrawal_reference": withdrawal.reference},
    )

    withdrawal.status = WithdrawalStatus.COMPLETED
    withdrawal.settlement_ledger_reference = settlement_reference
    withdrawal.reviewed_by_user_id = reviewer_user_id
    withdrawal.reviewed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(withdrawal)
    return withdrawal


async def reject_withdrawal(
    db: AsyncSession,
    ledger: LedgerClient,
    *,
    withdrawal: WithdrawalRequest,
    reviewer_user_id: str,
    reason: str,
) -> WithdrawalRequest:
    if withdrawal.status != WithdrawalStatus.PENDING_APPROVAL:
        raise InvalidWithdrawalStateError(
            f"withdrawal {withdrawal.id} is {withdrawal.status.value}, not pending_approval"
        )

    wallet = (await db.execute(select(Wallet).where(Wallet.id == withdrawal.wallet_id))).scalar_one()
    release_reference = f"{withdrawal.reference}:release"

    await ledger.post_transaction(
        reference=release_reference,
        source_type="internal_transfer",
        entries=[
            {
                "account_id": str(wallet.ledger_locked_account_id),
                "direction": "debit",
                "asset": withdrawal.asset,
                "amount": str(Decimal(withdrawal.amount)),
            },
            {
                "account_id": str(wallet.ledger_available_account_id),
                "direction": "credit",
                "asset": withdrawal.asset,
                "amount": str(Decimal(withdrawal.amount)),
            },
        ],
        description=f"Release lock: withdrawal {withdrawal.reference} rejected",
        metadata={
            "wallet_id": str(wallet.id),
            "withdrawal_reference": withdrawal.reference,
            "reason": reason,
        },
    )

    withdrawal.status = WithdrawalStatus.REJECTED
    withdrawal.settlement_ledger_reference = release_reference
    withdrawal.reviewed_by_user_id = reviewer_user_id
    withdrawal.reviewed_at = datetime.now(UTC)
    withdrawal.rejection_reason = reason
    await db.commit()
    await db.refresh(withdrawal)
    return withdrawal


async def internal_transfer(
    db: AsyncSession,
    ledger: LedgerClient,
    *,
    from_wallet: Wallet,
    to_wallet: Wallet,
    amount: Decimal,
    reference: str,
    metadata: dict | None = None,
) -> tuple[InternalTransfer, bool]:
    if from_wallet.asset != to_wallet.asset:
        raise WalletError(
            f"cannot transfer between wallets of different assets: {from_wallet.asset} vs {to_wallet.asset}"
        )

    existing = (
        await db.execute(select(InternalTransfer).where(InternalTransfer.reference == reference))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    await ledger.post_transaction(
        reference=reference,
        source_type="internal_transfer",
        entries=[
            {
                "account_id": str(from_wallet.ledger_available_account_id),
                "direction": "debit",
                "asset": from_wallet.asset,
                "amount": str(amount),
            },
            {
                "account_id": str(to_wallet.ledger_available_account_id),
                "direction": "credit",
                "asset": to_wallet.asset,
                "amount": str(amount),
            },
        ],
        description=f"Internal transfer of {amount} {from_wallet.asset}",
        metadata={
            "from_wallet_id": str(from_wallet.id),
            "to_wallet_id": str(to_wallet.id),
            **(metadata or {}),
        },
    )

    record = InternalTransfer(
        from_wallet_id=from_wallet.id,
        to_wallet_id=to_wallet.id,
        reference=reference,
        asset=from_wallet.asset,
        amount=amount,
        status=TransferStatus.COMPLETED,
        ledger_transaction_reference=reference,
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (
            await db.execute(select(InternalTransfer).where(InternalTransfer.reference == reference))
        ).scalar_one()
        return existing, False

    await db.refresh(record)
    return record, True
