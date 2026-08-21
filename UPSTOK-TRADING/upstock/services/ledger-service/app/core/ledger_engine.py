"""The double-entry posting engine.

This module is the *only* code in the system allowed to change a
LedgerAccount.balance value. Every other service (wallet, matching engine,
risk, settlement, admin) that needs to move value calls post_transaction()
over this service's API -- nothing ever does `account.balance += x`
anywhere else. That single choke point is what makes "every operation is
auditable and the books always balance" an enforced invariant instead of a
convention someone can forget.

Invariants enforced here, atomically, inside one DB transaction:
  1. At least two entries per transaction (a transaction with one leg isn't
     double-entry, it's a bug).
  2. Every entry amount is > 0 (direction encodes sign, not the amount).
  3. Per asset, sum(CREDIT amounts) == sum(DEBIT amounts). Multi-asset
     transactions (e.g. a trade that moves BTC one way and USDT the other)
     are allowed, but each asset must independently balance -- there is no
     such thing as a transaction that's only balanced "in aggregate" across
     different assets, because assets aren't fungible with each other at
     the ledger layer.
  4. Idempotent posting: re-posting an already-used `reference` returns the
     existing transaction unchanged rather than posting twice or erroring,
     so callers can safely retry after a timeout.
  5. Accounts touched by a transaction are locked (SELECT ... FOR UPDATE) in
     a deterministic order (sorted by account id) before any balance is
     read or written, so two concurrent transactions that touch overlapping
     accounts serialize instead of deadlocking or racing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import LedgerAccount
from app.models.entry import EntryDirection, LedgerEntry
from app.models.transaction import LedgerTransaction, TransactionSourceType, TransactionStatus


class LedgerError(Exception):
    """Base class for all engine-raised errors."""


class InvariantViolation(LedgerError):
    """Raised when a proposed transaction would not balance, or is otherwise
    structurally invalid. Never caught and "worked around" by callers --
    a transaction that fails this check must not be posted, full stop.
    """


class InsufficientBalanceError(LedgerError):
    """Raised when a debit would take a USER_* account negative. System
    accounts (SYSTEM_RESERVE etc.) are explicitly permitted to go negative,
    since e.g. SYSTEM_RESERVE going negative is exactly what "total user
    deposits exceed what the exchange has reserved" looks like, and that's
    a real state the engine must be able to represent, not error out on.
    """


class AccountNotFoundError(LedgerError):
    pass


@dataclass(frozen=True)
class EntryInput:
    account_id: str
    direction: EntryDirection
    asset: str
    amount: Decimal


ALLOW_NEGATIVE_BALANCE_TYPES = {"system_reserve", "system_suspense", "system_fee_revenue"}


def _validate_entries(entries: list[EntryInput], max_entries: int) -> None:
    if len(entries) < 2:
        raise InvariantViolation("a ledger transaction requires at least two entries")
    if len(entries) > max_entries:
        raise InvariantViolation(f"transaction exceeds max entries per transaction ({max_entries})")

    for e in entries:
        if e.amount <= 0:
            raise InvariantViolation(f"entry amount must be > 0, got {e.amount} on account {e.account_id}")

    # Per-asset debit/credit balance check.
    by_asset: dict[str, dict[str, Decimal]] = {}
    for e in entries:
        bucket = by_asset.setdefault(e.asset, {"debit": Decimal(0), "credit": Decimal(0)})
        bucket[e.direction.value] += e.amount

    for asset, sums in by_asset.items():
        if sums["debit"] != sums["credit"]:
            raise InvariantViolation(
                f"asset {asset} does not balance: debits={sums['debit']} credits={sums['credit']}"
            )


async def post_transaction(
    db: AsyncSession,
    *,
    reference: str,
    source_type: TransactionSourceType,
    entries: list[EntryInput],
    description: str = "",
    metadata: dict | None = None,
    max_entries: int | None = None,
) -> tuple[LedgerTransaction, list[LedgerEntry], bool]:
    """Post a balanced transaction. Returns (transaction, entries, created).

    `created` is False when `reference` already existed -- callers can use
    that to distinguish "I just posted this" from "this was already posted
    by an earlier attempt", which matters for e.g. deciding whether to send
    a fresh notification.
    """
    existing = await db.execute(select(LedgerTransaction).where(LedgerTransaction.reference == reference))
    existing_txn = existing.scalar_one_or_none()
    if existing_txn is not None:
        entries_result = await db.execute(
            select(LedgerEntry)
            .where(LedgerEntry.transaction_id == existing_txn.id)
            .order_by(LedgerEntry.created_at)
        )
        return existing_txn, list(entries_result.scalars().all()), False

    _validate_entries(entries, max_entries or 32)

    # Lock every touched account in a deterministic (id-sorted) order before
    # reading any balance, to make concurrent transactions that share an
    # account serialize rather than deadlock or read a stale balance.
    account_ids = sorted({e.account_id for e in entries})
    result = await db.execute(
        select(LedgerAccount)
        .where(LedgerAccount.id.in_(account_ids))
        .order_by(LedgerAccount.id)
        .with_for_update()
    )
    accounts_by_id = {str(a.id): a for a in result.scalars().all()}

    missing = set(account_ids) - set(accounts_by_id.keys())
    if missing:
        raise AccountNotFoundError(f"unknown ledger account id(s): {sorted(missing)}")

    for e in entries:
        account = accounts_by_id[e.account_id]
        if account.asset != e.asset:
            raise InvariantViolation(
                f"entry asset {e.asset} does not match account {account.id} asset {account.asset}"
            )

    txn = LedgerTransaction(
        reference=reference,
        source_type=source_type,
        status=TransactionStatus.POSTED,
        description=description,
        transaction_metadata=metadata or {},
        posted_at=datetime.now(UTC),
    )
    db.add(txn)
    await db.flush()  # assigns txn.id

    created_entries: list[LedgerEntry] = []
    for e in entries:
        account = accounts_by_id[e.account_id]
        delta = e.amount if e.direction == EntryDirection.CREDIT else -e.amount
        new_balance = Decimal(account.balance) + delta

        if new_balance < 0 and account.account_type.value not in ALLOW_NEGATIVE_BALANCE_TYPES:
            raise InsufficientBalanceError(
                f"account {account.id} ({account.account_type.value}, {account.asset}) "
                f"insufficient balance: has {account.balance}, needs {e.amount}"
            )

        account.balance = new_balance
        entry = LedgerEntry(
            transaction_id=txn.id,
            account_id=account.id,
            direction=e.direction,
            asset=e.asset,
            amount=e.amount,
            balance_after=new_balance,
        )
        db.add(entry)
        created_entries.append(entry)

    await db.commit()
    await db.refresh(txn)
    return txn, created_entries, True


@dataclass(frozen=True)
class ReconciliationResult:
    account_id: str
    cached_balance: Decimal
    computed_balance: Decimal
    entry_count: int

    @property
    def is_consistent(self) -> bool:
        return self.cached_balance == self.computed_balance


async def reconcile_account(db: AsyncSession, account_id: str) -> ReconciliationResult:
    """Recompute an account's balance from its full entry history and
    compare it against the cached LedgerAccount.balance column. These
    should NEVER diverge if post_transaction() is the only write path;
    this function exists so that invariant can be verified continuously
    (Phase 8 observability wires this into a scheduled consistency-check
    job) rather than merely assumed.
    """
    account_result = await db.execute(select(LedgerAccount).where(LedgerAccount.id == account_id))
    account = account_result.scalar_one_or_none()
    if account is None:
        raise AccountNotFoundError(f"unknown ledger account id: {account_id}")

    entries_result = await db.execute(select(LedgerEntry).where(LedgerEntry.account_id == account_id))
    entries = list(entries_result.scalars().all())

    computed = Decimal(0)
    for e in entries:
        computed += Decimal(e.amount) if e.direction == EntryDirection.CREDIT else -Decimal(e.amount)

    return ReconciliationResult(
        account_id=str(account.id),
        cached_balance=Decimal(account.balance),
        computed_balance=computed,
        entry_count=len(entries),
    )
