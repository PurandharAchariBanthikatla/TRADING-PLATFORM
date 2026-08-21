"""Test fixtures.

Runs against a real Postgres database (not SQLite) for the same reason as
api-gateway: native Postgres ENUM types, JSONB, and partial unique indexes
used by the ledger schema aren't faithfully emulated by SQLite. CI
provisions a throwaway postgres:16 service container; locally point
TEST_DATABASE_URL at a scratch database.
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

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db

# Imported before Base.metadata.create_all so the tables are registered.
from app.models import account as _account_model  # noqa: F401
from app.models import entry as _entry_model  # noqa: F401
from app.models import transaction as _transaction_model  # noqa: F401

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://exchange:exchange@localhost:5432/exchange_ledger_test",
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
async def client(db_session, db_engine) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override_get_db():
        # A fresh session per request -- not the fixed `db_session` fixture
        # -- so concurrent requests in a test (asyncio.gather) get
        # independent sessions just like separate real HTTP requests would
        # in production. Sharing one AsyncSession across concurrent
        # coroutines isn't just unrealistic, it's actively unsafe (SQLAlchemy
        # sessions aren't safe for concurrent use from multiple coroutines)
        # and would make concurrency tests fail on a test-harness artifact
        # rather than test real behavior.
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db

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
def admin_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token(str(uuid.uuid4()), 'admin')}"}


@pytest.fixture
def service_headers() -> dict:
    return {
        "X-Internal-Service-Key": settings.INTERNAL_SERVICE_KEY,
        "X-Internal-Service-Name": "wallet-service",
    }
