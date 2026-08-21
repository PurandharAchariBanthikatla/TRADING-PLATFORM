import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.event_bus import EventBus
from app.db.base import Base
from app.db.session import get_db
from app.models import asset as _asset_model  # noqa: F401
from app.models import candle as _candle_model  # noqa: F401
from app.models import market as _market_model  # noqa: F401
from app.models import orderbook as _orderbook_model  # noqa: F401
from app.models import trade as _trade_model  # noqa: F401
from app.models.market import Market, MarketStatus

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://exchange:exchange@localhost:5432/exchange_marketdata_test",
)
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/2")


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
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    client = redis.from_url(TEST_REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture
async def event_bus(redis_client) -> AsyncGenerator[EventBus, None]:
    bus = EventBus(redis_client)
    yield bus


@pytest_asyncio.fixture
async def client(db_session, db_engine, redis_client) -> AsyncGenerator[AsyncClient, None]:
    from app.main import app

    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    app.state.redis_client = redis_client
    app.state.event_bus = EventBus(redis_client)

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
def admin_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token(str(uuid.uuid4()), 'admin')}"}


@pytest.fixture
def user_headers() -> dict:
    return {"Authorization": f"Bearer {_make_token(str(uuid.uuid4()), 'user')}"}


@pytest_asyncio.fixture
async def sample_market(db_session) -> Market:
    market = Market(
        symbol=f"T{uuid.uuid4().hex[:6].upper()}-USDT",
        base_asset="TBTC",
        quote_asset="USDT",
        status=MarketStatus.TRADING,
        price_precision=2,
        quantity_precision=6,
        tick_size=Decimal("0.01"),
        lot_size=Decimal("0.0001"),
        min_quantity=Decimal("0.0001"),
        max_quantity=Decimal("100"),
        min_notional=Decimal("1"),
        maker_fee_bps=10,
        taker_fee_bps=15,
    )
    db_session.add(market)
    await db_session.commit()
    await db_session.refresh(market)
    return market
