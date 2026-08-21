from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CallerIdentity, get_caller, get_ledger_client, require_admin_or_service
from app.clients.ledger_client import (
    LedgerAccountNotFoundError,
    LedgerClient,
    LedgerInsufficientBalanceError,
    LedgerInvariantError,
    LedgerUnavailableError,
)
from app.core import wallet_engine
from app.core.logging import get_logger
from app.core.wallet_engine import InvalidWithdrawalStateError, WalletError, WithdrawalLimitExceededError
from app.db.session import get_db
from app.models.deposit import Deposit
from app.models.transfer import InternalTransfer
from app.models.wallet import Wallet
from app.models.withdrawal import WithdrawalRequest
from app.schemas.wallet import (
    DepositRequest,
    DepositResponse,
    InternalTransferRequest,
    InternalTransferResponse,
    WalletBalanceResponse,
    WalletCreateRequest,
    WalletResponse,
    WithdrawalRejectRequest,
    WithdrawalRequestCreate,
    WithdrawalResponse,
)

router = APIRouter(prefix="/wallet", tags=["wallet"])
log = get_logger(__name__)

_LEDGER_ERRORS = (
    LedgerInsufficientBalanceError,
    LedgerInvariantError,
    LedgerAccountNotFoundError,
    LedgerUnavailableError,
)


def _translate_ledger_error(exc: Exception) -> HTTPException:
    """Every route below calls into wallet_engine, which calls ledger-service
    through LedgerClient. Ledger-side rejections are re-mapped to HTTP
    statuses here in one place instead of once per route.
    """
    if isinstance(exc, LedgerInsufficientBalanceError):
        return HTTPException(status.HTTP_409_CONFLICT, detail=f"Insufficient balance: {exc}")
    if isinstance(exc, LedgerInvariantError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Ledger rejected transaction: {exc}"
        )
    if isinstance(exc, LedgerAccountNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"Ledger account not found: {exc}")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="Ledger service unavailable")


async def _get_owned_wallet(db: AsyncSession, wallet_id: str, caller: CallerIdentity) -> Wallet:
    wallet = (await db.execute(select(Wallet).where(Wallet.id == wallet_id))).scalar_one_or_none()
    if wallet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Wallet not found")
    if caller.role not in ("admin", "service") and str(wallet.user_id) != caller.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not authorized for this wallet")
    return wallet


@router.post("/wallets", response_model=WalletResponse, status_code=status.HTTP_200_OK)
async def create_or_get_wallet(
    payload: WalletCreateRequest,
    caller: CallerIdentity = Depends(get_caller),
    ledger: LedgerClient = Depends(get_ledger_client),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent get-or-create for the caller's own wallet. Provisions the
    three backing ledger accounts (available/locked/pending) on first call.
    """
    if caller.role == "service":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Service callers must use the admin-scoped provisioning path",
        )
    try:
        wallet = await wallet_engine.get_or_create_wallet(
            db, ledger, user_id=caller.user_id, asset=payload.asset
        )
    except LedgerUnavailableError as exc:
        raise _translate_ledger_error(exc) from exc
    return wallet


@router.get("/wallets/me", response_model=list[WalletResponse])
async def list_my_wallets(caller: CallerIdentity = Depends(get_caller), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Wallet).where(Wallet.user_id == caller.user_id).order_by(Wallet.asset))
    return list(result.scalars().all())


@router.get("/wallets/{wallet_id}/balance", response_model=WalletBalanceResponse)
async def get_wallet_balance(
    wallet_id: str,
    caller: CallerIdentity = Depends(get_caller),
    ledger: LedgerClient = Depends(get_ledger_client),
    db: AsyncSession = Depends(get_db),
):
    wallet = await _get_owned_wallet(db, wallet_id, caller)
    try:
        balances = await wallet_engine.get_wallet_balances(ledger, wallet)
    except LedgerUnavailableError as exc:
        raise _translate_ledger_error(exc) from exc

    return WalletBalanceResponse(
        wallet_id=str(wallet.id),
        asset=balances.asset,
        available=balances.available,
        locked=balances.locked,
        pending=balances.pending,
        total=balances.total,
    )


@router.post("/deposits", response_model=DepositResponse, status_code=status.HTTP_201_CREATED)
async def create_deposit(
    payload: DepositRequest,
    caller: CallerIdentity = Depends(get_caller),
    ledger: LedgerClient = Depends(get_ledger_client),
    db: AsyncSession = Depends(get_db),
):
    """Paper deposit into the caller's own wallet for the given asset,
    creating the wallet first if it doesn't exist yet. There is no real
    funding source behind this -- it is a sandbox faucet, not a payment
    rail; see the module docstring on wallet_engine.deposit.
    """
    if caller.role == "service":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service callers are not yet supported here"
        )

    wallet = await wallet_engine.get_or_create_wallet(db, ledger, user_id=caller.user_id, asset=payload.asset)

    try:
        deposit, created = await wallet_engine.deposit(
            db,
            ledger,
            wallet=wallet,
            amount=payload.amount,
            reference=payload.reference,
            metadata=payload.metadata,
        )
    except _LEDGER_ERRORS as exc:
        raise _translate_ledger_error(exc) from exc

    log.info(
        "wallet_deposit",
        wallet_id=str(wallet.id),
        reference=deposit.reference,
        amount=str(deposit.amount),
        asset=deposit.asset,
        idempotent_replay=not created,
    )
    return deposit


@router.get("/wallets/{wallet_id}/deposits", response_model=list[DepositResponse])
async def list_wallet_deposits(
    wallet_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: CallerIdentity = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_wallet(db, wallet_id, caller)
    result = await db.execute(
        select(Deposit)
        .where(Deposit.wallet_id == wallet_id)
        .order_by(Deposit.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.post("/withdrawals", response_model=WithdrawalResponse, status_code=status.HTTP_201_CREATED)
async def create_withdrawal(
    payload: WithdrawalRequestCreate,
    caller: CallerIdentity = Depends(get_caller),
    ledger: LedgerClient = Depends(get_ledger_client),
    db: AsyncSession = Depends(get_db),
):
    """Requests a withdrawal from the caller's own wallet. Locks the funds
    immediately (available -> locked) and leaves the request pending admin
    approval -- see wallet_engine.request_withdrawal.
    """
    if caller.role == "service":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service callers are not yet supported here"
        )

    wallet = await wallet_engine.get_or_create_wallet(db, ledger, user_id=caller.user_id, asset=payload.asset)

    try:
        withdrawal, created = await wallet_engine.request_withdrawal(
            db,
            ledger,
            wallet=wallet,
            amount=payload.amount,
            destination=payload.destination,
            reference=payload.reference,
            metadata=payload.metadata,
        )
    except WithdrawalLimitExceededError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except _LEDGER_ERRORS as exc:
        raise _translate_ledger_error(exc) from exc

    log.info(
        "wallet_withdrawal_requested",
        wallet_id=str(wallet.id),
        reference=withdrawal.reference,
        amount=str(withdrawal.amount),
        asset=withdrawal.asset,
        idempotent_replay=not created,
    )
    return withdrawal


@router.get("/wallets/{wallet_id}/withdrawals", response_model=list[WithdrawalResponse])
async def list_wallet_withdrawals(
    wallet_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: CallerIdentity = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_wallet(db, wallet_id, caller)
    result = await db.execute(
        select(WithdrawalRequest)
        .where(WithdrawalRequest.wallet_id == wallet_id)
        .order_by(WithdrawalRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def _get_withdrawal_or_404(db: AsyncSession, withdrawal_id: str) -> WithdrawalRequest:
    withdrawal = (
        await db.execute(select(WithdrawalRequest).where(WithdrawalRequest.id == withdrawal_id))
    ).scalar_one_or_none()
    if withdrawal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Withdrawal request not found")
    return withdrawal


@router.post("/withdrawals/{withdrawal_id}/approve", response_model=WithdrawalResponse)
async def approve_withdrawal(
    withdrawal_id: str,
    admin: CallerIdentity = Depends(require_admin_or_service),
    ledger: LedgerClient = Depends(get_ledger_client),
    db: AsyncSession = Depends(get_db),
):
    withdrawal = await _get_withdrawal_or_404(db, withdrawal_id)
    try:
        withdrawal = await wallet_engine.approve_withdrawal(
            db, ledger, withdrawal=withdrawal, reviewer_user_id=admin.user_id
        )
    except InvalidWithdrawalStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except _LEDGER_ERRORS as exc:
        raise _translate_ledger_error(exc) from exc

    log.info("wallet_withdrawal_approved", withdrawal_id=str(withdrawal.id), reviewer=admin.user_id)
    return withdrawal


@router.post("/withdrawals/{withdrawal_id}/reject", response_model=WithdrawalResponse)
async def reject_withdrawal(
    withdrawal_id: str,
    payload: WithdrawalRejectRequest,
    admin: CallerIdentity = Depends(require_admin_or_service),
    ledger: LedgerClient = Depends(get_ledger_client),
    db: AsyncSession = Depends(get_db),
):
    withdrawal = await _get_withdrawal_or_404(db, withdrawal_id)
    try:
        withdrawal = await wallet_engine.reject_withdrawal(
            db, ledger, withdrawal=withdrawal, reviewer_user_id=admin.user_id, reason=payload.reason
        )
    except InvalidWithdrawalStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except _LEDGER_ERRORS as exc:
        raise _translate_ledger_error(exc) from exc

    log.info("wallet_withdrawal_rejected", withdrawal_id=str(withdrawal.id), reviewer=admin.user_id)
    return withdrawal


@router.post("/transfers", response_model=InternalTransferResponse, status_code=status.HTTP_201_CREATED)
async def create_internal_transfer(
    payload: InternalTransferRequest,
    caller: CallerIdentity = Depends(get_caller),
    ledger: LedgerClient = Depends(get_ledger_client),
    db: AsyncSession = Depends(get_db),
):
    if caller.role == "service":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Service callers are not yet supported here"
        )
    if payload.to_user_id == caller.user_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot transfer to your own wallet")

    from_wallet = await wallet_engine.get_or_create_wallet(
        db, ledger, user_id=caller.user_id, asset=payload.asset
    )
    to_wallet = await wallet_engine.get_or_create_wallet(
        db, ledger, user_id=payload.to_user_id, asset=payload.asset
    )

    try:
        transfer, created = await wallet_engine.internal_transfer(
            db,
            ledger,
            from_wallet=from_wallet,
            to_wallet=to_wallet,
            amount=payload.amount,
            reference=payload.reference,
            metadata=payload.metadata,
        )
    except WalletError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except _LEDGER_ERRORS as exc:
        raise _translate_ledger_error(exc) from exc

    log.info(
        "wallet_internal_transfer",
        from_wallet_id=str(from_wallet.id),
        to_wallet_id=str(to_wallet.id),
        reference=transfer.reference,
        amount=str(transfer.amount),
        idempotent_replay=not created,
    )
    return transfer


@router.get("/wallets/{wallet_id}/transfers", response_model=list[InternalTransferResponse])
async def list_wallet_transfers(
    wallet_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: CallerIdentity = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
):
    await _get_owned_wallet(db, wallet_id, caller)
    result = await db.execute(
        select(InternalTransfer)
        .where((InternalTransfer.from_wallet_id == wallet_id) | (InternalTransfer.to_wallet_id == wallet_id))
        .order_by(InternalTransfer.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())
