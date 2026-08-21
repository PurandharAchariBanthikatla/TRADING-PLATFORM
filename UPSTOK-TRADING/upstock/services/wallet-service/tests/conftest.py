"""Test fixtures.

Unlike a typical service-boundary test setup that stubs out the downstream
dependency, these tests call a REAL, running ledger-service instance over
HTTP (see LEDGER_SERVICE_BASE_URL). The point of the Wallet module is that
it correctly drives the double-entry engine -- a mocked ledger client would
only prove wallet-service formats requests correctly, not that a deposit
actually, provably balances the books. Running against the real service is
slower but is the only way to genuinely verify the integration this phase
is about.
"""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.clients.ledger_client import LedgerClient
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.models import deposit as _deposit_model  # noqa: F401
from app.models import transfer as _transfer_model  # noqa: F401
from app.models import wallet as _wallet_model  # noqa: F401
from app.models import withdrawal as _withdrawal_model  # noqa: F401

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://exchange:exchange@localhost:5432/exchange_wallet_test",
)


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def ledger_client() -> AsyncGenerator[LedgerClient, None]:
    client = LedgerClient()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def client(db_session, ledger_client) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.state.ledger_client = ledger_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


def _make_token(user_id: str, role: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "type": "access",
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=15),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def user_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def user_headers(user_id) -> dict:
    return {"Authorization": f"Bearer {_make_token(user_id, 'user')}"}


@pytest.fixture
def other_user_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def other_user_headers(other_user_id) -> dict:
    return {"Authorization": f"Bearer {_make_token(other_user_id, 'user')}"}


@pytest.fixture
def admin_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token(str(uuid.uuid4()), 'admin')}"}


@pytest.fixture
def unique_asset() -> str:
    """A fresh, never-before-used asset symbol per test. ledger-service's
    SYSTEM_RESERVE account is a singleton per asset, so reusing an asset
    across tests would make balance assertions depend on execution order;
    a unique symbol per test keeps each test's ledger state isolated even
    though all tests share the one live ledger-service instance/database.
    """
    return f"T{uuid.uuid4().hex[:8].upper()}"
