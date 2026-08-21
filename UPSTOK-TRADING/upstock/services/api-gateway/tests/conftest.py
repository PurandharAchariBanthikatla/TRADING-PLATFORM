"""Test fixtures.

Deliberately run against a real Postgres database rather than SQLite: the
schema uses Postgres-specific types (UUID, native ENUM) and the trading /
ledger services this gateway will eventually sit beside rely on Postgres
transactional semantics that SQLite doesn't faithfully emulate. CI provisions
a throwaway `postgres:16` service container (see .github/workflows/ci.yml);
locally, point TEST_DATABASE_URL at a scratch database via
`scripts/docker-run.sh` and its default credentials.
"""
import os
import uuid
from collections.abc import AsyncGenerator

import fakeredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.core.rate_limit as rate_limit_module
from app.db.base import Base
from app.db.session import get_db

# Must be imported before Base.metadata.create_all runs below, or the
# users/refresh_tokens tables never get registered on the metadata and
# create_all silently creates nothing.
from app.models import refresh_token as _refresh_token_model  # noqa: F401
from app.models import user as _user_model  # noqa: F401

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://exchange:exchange@localhost:5432/exchange_test",
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
async def client(db_session, monkeypatch) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    # Swap the real Redis client for an in-memory fake so unit tests don't
    # need a live Redis instance; rate-limit / denylist logic still runs for
    # real against it. Integration tests exercise real Redis via CI services.
    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(rate_limit_module, "_redis", fake)
    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: fake)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"
