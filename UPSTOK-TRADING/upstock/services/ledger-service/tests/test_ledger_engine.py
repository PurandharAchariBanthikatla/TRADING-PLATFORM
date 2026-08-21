import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.ledger_engine import (
    AccountNotFoundError,
    EntryInput,
    InsufficientBalanceError,
    InvariantViolation,
    post_transaction,
    reconcile_account,
)
from app.models.account import AccountType, LedgerAccount, OwnerType
from app.models.entry import EntryDirection
from app.models.transaction import TransactionSourceType


async def _make_account(
    db, *, owner_type=OwnerType.USER, owner_id=None, asset="BTC", account_type=AccountType.USER_AVAILABLE
):
    account = LedgerAccount(
        owner_type=owner_type,
        owner_id=owner_id or (uuid.uuid4() if owner_type == OwnerType.USER else None),
        asset=asset,
        account_type=account_type,
        balance=Decimal(0),
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@pytest.mark.asyncio
async def test_balanced_deposit_updates_both_accounts(db_session):
    reserve = await _make_account(
        db_session, owner_type=OwnerType.SYSTEM, asset="BTC", account_type=AccountType.SYSTEM_RESERVE
    )
    user_acct = await _make_account(db_session, asset="BTC")

    txn, entries, created = await post_transaction(
        db_session,
        reference="deposit-1",
        source_type=TransactionSourceType.DEPOSIT,
        entries=[
            EntryInput(str(reserve.id), EntryDirection.DEBIT, "BTC", Decimal("1.5")),
            EntryInput(str(user_acct.id), EntryDirection.CREDIT, "BTC", Decimal("1.5")),
        ],
    )

    assert created is True
    assert len(entries) == 2

    refreshed_user = (
        await db_session.execute(select(LedgerAccount).where(LedgerAccount.id == user_acct.id))
    ).scalar_one()
    refreshed_reserve = (
        await db_session.execute(select(LedgerAccount).where(LedgerAccount.id == reserve.id))
    ).scalar_one()
    assert Decimal(refreshed_user.balance) == Decimal("1.5")
    assert Decimal(refreshed_reserve.balance) == Decimal("-1.5")


@pytest.mark.asyncio
async def test_unbalanced_transaction_is_rejected(db_session):
    reserve = await _make_account(
        db_session, owner_type=OwnerType.SYSTEM, account_type=AccountType.SYSTEM_RESERVE
    )
    user_acct = await _make_account(db_session)

    with pytest.raises(InvariantViolation):
        await post_transaction(
            db_session,
            reference="bad-1",
            source_type=TransactionSourceType.DEPOSIT,
            entries=[
                EntryInput(str(reserve.id), EntryDirection.DEBIT, "BTC", Decimal("1.0")),
                EntryInput(str(user_acct.id), EntryDirection.CREDIT, "BTC", Decimal("0.9")),
            ],
        )

    # A rejected transaction must not have moved anything.
    refreshed_user = (
        await db_session.execute(select(LedgerAccount).where(LedgerAccount.id == user_acct.id))
    ).scalar_one()
    assert Decimal(refreshed_user.balance) == Decimal(0)


@pytest.mark.asyncio
async def test_single_entry_transaction_is_rejected(db_session):
    user_acct = await _make_account(db_session)
    with pytest.raises(InvariantViolation):
        await post_transaction(
            db_session,
            reference="single-1",
            source_type=TransactionSourceType.ADJUSTMENT,
            entries=[EntryInput(str(user_acct.id), EntryDirection.CREDIT, "BTC", Decimal("1.0"))],
        )


@pytest.mark.asyncio
async def test_user_account_cannot_go_negative(db_session):
    reserve = await _make_account(
        db_session, owner_type=OwnerType.SYSTEM, account_type=AccountType.SYSTEM_RESERVE
    )
    user_acct = await _make_account(db_session)

    with pytest.raises(InsufficientBalanceError):
        await post_transaction(
            db_session,
            reference="withdraw-1",
            source_type=TransactionSourceType.WITHDRAWAL,
            entries=[
                EntryInput(str(user_acct.id), EntryDirection.DEBIT, "BTC", Decimal("1.0")),
                EntryInput(str(reserve.id), EntryDirection.CREDIT, "BTC", Decimal("1.0")),
            ],
        )


@pytest.mark.asyncio
async def test_system_reserve_account_may_go_negative(db_session):
    reserve = await _make_account(
        db_session, owner_type=OwnerType.SYSTEM, account_type=AccountType.SYSTEM_RESERVE
    )
    user_acct = await _make_account(db_session)

    # Deposits legitimately push SYSTEM_RESERVE negative (from the
    # exchange's perspective it now owes the user this BTC).
    txn, _, _ = await post_transaction(
        db_session,
        reference="deposit-neg-1",
        source_type=TransactionSourceType.DEPOSIT,
        entries=[
            EntryInput(str(reserve.id), EntryDirection.DEBIT, "BTC", Decimal("2.0")),
            EntryInput(str(user_acct.id), EntryDirection.CREDIT, "BTC", Decimal("2.0")),
        ],
    )
    assert txn is not None


@pytest.mark.asyncio
async def test_idempotent_replay_does_not_double_post(db_session):
    reserve = await _make_account(
        db_session, owner_type=OwnerType.SYSTEM, account_type=AccountType.SYSTEM_RESERVE
    )
    user_acct = await _make_account(db_session)

    entries = [
        EntryInput(str(reserve.id), EntryDirection.DEBIT, "BTC", Decimal("1.0")),
        EntryInput(str(user_acct.id), EntryDirection.CREDIT, "BTC", Decimal("1.0")),
    ]

    txn1, _, created1 = await post_transaction(
        db_session, reference="idem-1", source_type=TransactionSourceType.DEPOSIT, entries=entries
    )
    txn2, _, created2 = await post_transaction(
        db_session, reference="idem-1", source_type=TransactionSourceType.DEPOSIT, entries=entries
    )

    assert created1 is True
    assert created2 is False
    assert txn1.id == txn2.id

    refreshed_user = (
        await db_session.execute(select(LedgerAccount).where(LedgerAccount.id == user_acct.id))
    ).scalar_one()
    # Balance reflects exactly one deposit, not two.
    assert Decimal(refreshed_user.balance) == Decimal("1.0")


@pytest.mark.asyncio
async def test_multi_asset_transaction_must_balance_per_asset(db_session):
    """A trade-style transaction moves two different assets in opposite
    directions through per-asset clearing accounts. Each asset's debits and
    credits must balance independently -- BTC moving is not allowed to
    "cancel out" against USDT moving.
    """
    btc_clearing = await _make_account(
        db_session, owner_type=OwnerType.SYSTEM, asset="BTC", account_type=AccountType.SYSTEM_SUSPENSE
    )
    usdt_clearing = await _make_account(
        db_session, owner_type=OwnerType.SYSTEM, asset="USDT", account_type=AccountType.SYSTEM_SUSPENSE
    )
    buyer_btc = await _make_account(db_session, asset="BTC")
    seller_usdt = await _make_account(db_session, asset="USDT")

    txn, entries, created = await post_transaction(
        db_session,
        reference="trade-1",
        source_type=TransactionSourceType.TRADE,
        entries=[
            EntryInput(str(btc_clearing.id), EntryDirection.DEBIT, "BTC", Decimal("0.1")),
            EntryInput(str(buyer_btc.id), EntryDirection.CREDIT, "BTC", Decimal("0.1")),
            EntryInput(str(usdt_clearing.id), EntryDirection.DEBIT, "USDT", Decimal("5000")),
            EntryInput(str(seller_usdt.id), EntryDirection.CREDIT, "USDT", Decimal("5000")),
        ],
    )
    assert created is True
    assert len(entries) == 4


@pytest.mark.asyncio
async def test_unknown_account_is_rejected(db_session):
    user_acct = await _make_account(db_session)
    with pytest.raises(AccountNotFoundError):
        await post_transaction(
            db_session,
            reference="unknown-acct-1",
            source_type=TransactionSourceType.ADJUSTMENT,
            entries=[
                EntryInput(str(user_acct.id), EntryDirection.CREDIT, "BTC", Decimal("1.0")),
                EntryInput(str(uuid.uuid4()), EntryDirection.DEBIT, "BTC", Decimal("1.0")),
            ],
        )


@pytest.mark.asyncio
async def test_reconciliation_matches_after_multiple_transactions(db_session):
    reserve = await _make_account(
        db_session, owner_type=OwnerType.SYSTEM, account_type=AccountType.SYSTEM_RESERVE
    )
    user_acct = await _make_account(db_session)

    for i in range(5):
        await post_transaction(
            db_session,
            reference=f"deposit-multi-{i}",
            source_type=TransactionSourceType.DEPOSIT,
            entries=[
                EntryInput(str(reserve.id), EntryDirection.DEBIT, "BTC", Decimal("0.2")),
                EntryInput(str(user_acct.id), EntryDirection.CREDIT, "BTC", Decimal("0.2")),
            ],
        )

    result = await reconcile_account(db_session, str(user_acct.id))
    assert result.is_consistent
    assert result.computed_balance == Decimal("1.0")
    assert result.entry_count == 5


@pytest.mark.asyncio
async def test_concurrent_deposits_to_same_account_serialize_correctly(db_engine):
    """Two concurrent transactions crediting the same account must not lose
    an update -- the FOR UPDATE lock in post_transaction should serialize
    them so both credits land, not just one (a classic lost-update race).
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async with session_factory() as setup_session:
        reserve = await _make_account(
            setup_session, owner_type=OwnerType.SYSTEM, account_type=AccountType.SYSTEM_RESERVE
        )
        user_acct = await _make_account(setup_session)
        reserve_id, user_id = str(reserve.id), str(user_acct.id)

    async def _deposit(ref: str):
        async with session_factory() as session:
            await post_transaction(
                session,
                reference=ref,
                source_type=TransactionSourceType.DEPOSIT,
                entries=[
                    EntryInput(reserve_id, EntryDirection.DEBIT, "BTC", Decimal("0.5")),
                    EntryInput(user_id, EntryDirection.CREDIT, "BTC", Decimal("0.5")),
                ],
            )

    await asyncio.gather(_deposit("concurrent-1"), _deposit("concurrent-2"))

    async with session_factory() as check_session:
        refreshed = (
            await check_session.execute(select(LedgerAccount).where(LedgerAccount.id == user_id))
        ).scalar_one()
        assert Decimal(refreshed.balance) == Decimal("1.0")
