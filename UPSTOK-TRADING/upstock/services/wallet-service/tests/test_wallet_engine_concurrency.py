import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.clients.ledger_client import LedgerInsufficientBalanceError
from app.core import wallet_engine
from app.models.wallet import Wallet
from app.models.withdrawal import WithdrawalStatus


@pytest.mark.asyncio
async def test_concurrent_withdrawal_requests_do_not_overdraw(db_engine, ledger_client, unique_asset):
    """Two concurrent withdrawal requests together exceeding the available
    balance must not both succeed -- the ledger's FOR UPDATE locking
    (exercised transitively through wallet_engine here) must let exactly
    one lock succeed and reject the other with insufficient balance.
    """
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async with session_factory() as setup_session:
        wallet = await wallet_engine.get_or_create_wallet(
            setup_session, ledger_client, user_id=str(uuid.uuid4()), asset=unique_asset
        )
        await wallet_engine.deposit(
            setup_session, ledger_client, wallet=wallet, amount=Decimal("10"), reference=f"dep-{uuid.uuid4()}"
        )
        wallet_id = wallet.id

    results = []

    async def _attempt_withdrawal(amount: Decimal, ref: str):
        async with session_factory() as session:
            w = (await session.execute(select(Wallet).where(Wallet.id == wallet_id))).scalar_one()
            try:
                await wallet_engine.request_withdrawal(
                    session, ledger_client, wallet=w, amount=amount, destination="x", reference=ref
                )
                results.append("ok")
            except LedgerInsufficientBalanceError:
                results.append("insufficient")

    # 6 + 6 > 10 available -- exactly one of these must fail.
    await asyncio.gather(
        _attempt_withdrawal(Decimal("6"), f"race-a-{uuid.uuid4()}"),
        _attempt_withdrawal(Decimal("6"), f"race-b-{uuid.uuid4()}"),
    )

    assert sorted(results) == ["insufficient", "ok"]

    async with session_factory() as check_session:
        w = (await check_session.execute(select(Wallet).where(Wallet.id == wallet_id))).scalar_one()
        balances = await wallet_engine.get_wallet_balances(ledger_client, w)
        # Never negative, never double-spent: exactly 4 left available (10 - 6).
        assert balances.available == Decimal("4")
        assert balances.locked == Decimal("6")


@pytest.mark.asyncio
async def test_cannot_reject_an_already_rejected_withdrawal(db_engine, ledger_client, unique_asset):
    """Rejecting an already-rejected withdrawal must fail loudly rather
    than silently re-releasing funds that were already released once.
    """
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async with session_factory() as session:
        wallet = await wallet_engine.get_or_create_wallet(
            session, ledger_client, user_id=str(uuid.uuid4()), asset=unique_asset
        )
        await wallet_engine.deposit(
            session, ledger_client, wallet=wallet, amount=Decimal("5"), reference=f"dep-{uuid.uuid4()}"
        )
        withdrawal, _ = await wallet_engine.request_withdrawal(
            session,
            ledger_client,
            wallet=wallet,
            amount=Decimal("2"),
            destination="x",
            reference=f"wd-{uuid.uuid4()}",
        )

        rejected = await wallet_engine.reject_withdrawal(
            session, ledger_client, withdrawal=withdrawal, reviewer_user_id=str(uuid.uuid4()), reason="test"
        )
        assert rejected.status == WithdrawalStatus.REJECTED

        with pytest.raises(wallet_engine.InvalidWithdrawalStateError):
            await wallet_engine.reject_withdrawal(
                session,
                ledger_client,
                withdrawal=rejected,
                reviewer_user_id=str(uuid.uuid4()),
                reason="test again",
            )


@pytest.mark.asyncio
async def test_wallet_creation_is_idempotent_under_concurrency(db_engine, ledger_client, unique_asset):
    """Two concurrent get_or_create_wallet() calls for the same
    (user_id, asset) must converge on exactly one wallet row, not two.
    """
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    user_id = str(uuid.uuid4())

    async def _create():
        async with session_factory() as session:
            return await wallet_engine.get_or_create_wallet(
                session, ledger_client, user_id=user_id, asset=unique_asset
            )

    wallets = await asyncio.gather(_create(), _create(), _create())
    ids = {str(w.id) for w in wallets}
    assert len(ids) == 1
