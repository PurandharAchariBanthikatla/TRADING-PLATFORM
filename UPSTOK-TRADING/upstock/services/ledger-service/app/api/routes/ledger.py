from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CallerIdentity, get_caller, require_admin_or_service
from app.core.config import settings
from app.core.ledger_engine import (
    AccountNotFoundError,
    EntryInput,
    InsufficientBalanceError,
    InvariantViolation,
    post_transaction,
    reconcile_account,
)
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.account import LedgerAccount, OwnerType
from app.models.entry import LedgerEntry
from app.models.transaction import LedgerTransaction
from app.schemas.ledger import (
    AccountCreateRequest,
    AccountResponse,
    EntryResponse,
    PostTransactionRequest,
    ReconciliationResponse,
    TransactionResponse,
)

router = APIRouter(prefix="/ledger", tags=["ledger"])
log = get_logger(__name__)


def _assert_can_view_account(account: LedgerAccount, caller: CallerIdentity) -> None:
    if caller.role in ("admin", "service"):
        return
    if account.owner_type == OwnerType.USER and str(account.owner_id) == caller.user_id:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not authorized to view this account")


@router.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_200_OK)
async def get_or_create_account(
    payload: AccountCreateRequest,
    caller: CallerIdentity = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent get-or-create. A user may only create/fetch their own
    USER_* accounts. SYSTEM_* accounts (there is exactly one per
    asset+account_type -- enforced by a DB partial unique index) and
    USER_* accounts on behalf of a different owner can only be provisioned
    by an admin or a trusted internal service (e.g. wallet-service
    provisioning a user's wallet accounts).
    """
    if payload.owner_type == OwnerType.SYSTEM:
        if caller.role not in ("admin", "service"):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Only admins or internal services may provision system accounts",
            )
        if payload.owner_id is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="System accounts must not set owner_id"
            )
        owner_id = None
    else:
        if payload.owner_id is None:
            if caller.role == "service":
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY, detail="owner_id is required for service callers"
                )
            payload_owner_id = caller.user_id
        else:
            payload_owner_id = payload.owner_id
        if caller.role not in ("admin", "service") and payload_owner_id != caller.user_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="Cannot create a ledger account for another user"
            )
        owner_id = payload_owner_id

    query = select(LedgerAccount).where(
        LedgerAccount.owner_type == payload.owner_type,
        LedgerAccount.asset == payload.asset,
        LedgerAccount.account_type == payload.account_type,
    )
    query = (
        query.where(LedgerAccount.owner_id == owner_id)
        if owner_id
        else query.where(LedgerAccount.owner_id.is_(None))
    )
    existing = (await db.execute(query)).scalar_one_or_none()
    if existing is not None:
        return existing

    account = LedgerAccount(
        owner_type=payload.owner_type,
        owner_id=owner_id,
        asset=payload.asset,
        account_type=payload.account_type,
        balance=Decimal(0),
    )
    db.add(account)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a race with a concurrent get-or-create for the same
        # (owner_id, asset, account_type) -- the SELECT above and this
        # INSERT aren't atomic together, so two simultaneous callers can
        # both pass the SELECT and both attempt the INSERT. The DB's
        # partial unique index is the real guard; this just means the
        # loser here returns the winner's row instead of a 500.
        await db.rollback()
        existing = (await db.execute(query)).scalar_one()
        return existing

    await db.refresh(account)
    log.info(
        "ledger_account_created",
        account_id=str(account.id),
        owner_type=account.owner_type.value,
        asset=account.asset,
        account_type=account.account_type.value,
    )
    return account


@router.get("/accounts/me", response_model=list[AccountResponse])
async def list_my_accounts(
    asset: str | None = Query(default=None),
    caller: CallerIdentity = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
):
    query = select(LedgerAccount).where(
        LedgerAccount.owner_type == OwnerType.USER,
        LedgerAccount.owner_id == caller.user_id,
    )
    if asset:
        query = query.where(LedgerAccount.asset == asset.upper())
    result = await db.execute(query.order_by(LedgerAccount.asset, LedgerAccount.account_type))
    return list(result.scalars().all())


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    caller: CallerIdentity = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(LedgerAccount).where(LedgerAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Account not found")
    _assert_can_view_account(account, caller)
    return account


@router.get("/accounts/{account_id}/entries", response_model=list[EntryResponse])
async def get_account_entries(
    account_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    caller: CallerIdentity = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
):
    account_result = await db.execute(select(LedgerAccount).where(LedgerAccount.id == account_id))
    account = account_result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Account not found")
    _assert_can_view_account(account, caller)

    result = await db.execute(
        select(LedgerEntry)
        .where(LedgerEntry.account_id == account_id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


@router.get("/accounts/{account_id}/reconcile", response_model=ReconciliationResponse)
async def get_account_reconciliation(
    account_id: str,
    _caller: CallerIdentity = Depends(require_admin_or_service),
    db: AsyncSession = Depends(get_db),
):
    """Recompute the account balance from its entry history and compare
    against the cached balance. Any divergence here is a P0 -- it means the
    accounting-invariant guarantee in app.core.ledger_engine was violated
    (e.g. by a direct DB write bypassing post_transaction()), not that the
    account is merely "out of date".
    """
    try:
        result = await reconcile_account(db, account_id)
    except AccountNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if not result.is_consistent:
        log.error(
            "ledger_reconciliation_drift",
            account_id=account_id,
            cached_balance=str(result.cached_balance),
            computed_balance=str(result.computed_balance),
        )

    return ReconciliationResponse(
        account_id=result.account_id,
        cached_balance=result.cached_balance,
        computed_balance=result.computed_balance,
        entry_count=result.entry_count,
        is_consistent=result.is_consistent,
    )


@router.post("/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: PostTransactionRequest,
    _caller: CallerIdentity = Depends(require_admin_or_service),
    db: AsyncSession = Depends(get_db),
):
    """The single write path for moving value between ledger accounts.

    Restricted to admins and trusted internal services (via the
    X-Internal-Service-Key header, see app/api/deps.py) -- end users never
    call this directly. wallet-service is the first real caller; matching/
    risk/settlement services will be others in later phases.
    """
    entries = [
        EntryInput(account_id=e.account_id, direction=e.direction, asset=e.asset, amount=e.amount)
        for e in payload.entries
    ]

    try:
        txn, entry_rows, created = await post_transaction(
            db,
            reference=payload.reference,
            source_type=payload.source_type,
            entries=entries,
            description=payload.description,
            metadata=payload.metadata,
            max_entries=settings.MAX_ENTRIES_PER_TRANSACTION,
        )
    except InvariantViolation as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except InsufficientBalanceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AccountNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    log.info(
        "ledger_transaction_posted",
        transaction_id=str(txn.id),
        reference=txn.reference,
        source_type=txn.source_type.value,
        entry_count=len(entry_rows),
        idempotent_replay=not created,
    )

    response = TransactionResponse.model_validate(txn)
    response.entries = [EntryResponse.model_validate(e) for e in entry_rows]
    return response


@router.get("/transactions/{reference}", response_model=TransactionResponse)
async def get_transaction(
    reference: str,
    _caller: CallerIdentity = Depends(require_admin_or_service),
    db: AsyncSession = Depends(get_db),
):
    txn = (
        await db.execute(select(LedgerTransaction).where(LedgerTransaction.reference == reference))
    ).scalar_one_or_none()
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    entries = (
        (
            await db.execute(
                select(LedgerEntry)
                .where(LedgerEntry.transaction_id == txn.id)
                .order_by(LedgerEntry.created_at)
            )
        )
        .scalars()
        .all()
    )

    response = TransactionResponse.model_validate(txn)
    response.entries = [EntryResponse.model_validate(e) for e in entries]
    return response
