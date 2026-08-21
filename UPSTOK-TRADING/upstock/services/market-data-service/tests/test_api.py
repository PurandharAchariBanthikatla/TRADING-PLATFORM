import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core.candle_aggregator import handle_trade_event
from app.core.orderbook_simulator import generate_snapshot
from app.core.simulator import generate_next_trade, init_market_sim_state
from app.schemas.events import TradeEvent


@pytest.mark.asyncio
async def test_health_live(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_create_asset_requires_admin(client, user_headers):
    resp = await client.post(
        "/api/v1/assets", json={"symbol": "XYZ", "name": "Test Coin"}, headers=user_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_and_list_assets(client, admin_headers):
    symbol = f"A{uuid.uuid4().hex[:6].upper()}"
    resp = await client.post(
        "/api/v1/assets", json={"symbol": symbol, "name": "Test Asset", "decimals": 6}, headers=admin_headers
    )
    assert resp.status_code == 201
    assert resp.json()["symbol"] == symbol

    listing = await client.get("/api/v1/assets")
    assert listing.status_code == 200
    assert any(a["symbol"] == symbol for a in listing.json())


@pytest.mark.asyncio
async def test_duplicate_asset_symbol_conflicts(client, admin_headers):
    symbol = f"A{uuid.uuid4().hex[:6].upper()}"
    payload = {"symbol": symbol, "name": "Test Asset"}
    first = await client.post("/api/v1/assets", json=payload, headers=admin_headers)
    second = await client.post("/api/v1/assets", json=payload, headers=admin_headers)
    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_create_market_and_get_by_symbol(client, admin_headers):
    base = f"B{uuid.uuid4().hex[:6].upper()}"
    resp = await client.post(
        "/api/v1/markets",
        json={
            "base_asset": base,
            "quote_asset": "USDT",
            "price_precision": 2,
            "quantity_precision": 4,
            "tick_size": "0.01",
            "lot_size": "0.0001",
            "min_quantity": "0.0001",
            "max_quantity": "100",
            "min_notional": "1",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    symbol = resp.json()["symbol"]
    assert symbol == f"{base}-USDT"

    fetched = await client.get(f"/api/v1/markets/{symbol}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "trading"


@pytest.mark.asyncio
async def test_market_creation_rejects_max_not_greater_than_min(client, admin_headers):
    base = f"C{uuid.uuid4().hex[:6].upper()}"
    resp = await client.post(
        "/api/v1/markets",
        json={
            "base_asset": base,
            "quote_asset": "USDT",
            "price_precision": 2,
            "quantity_precision": 4,
            "tick_size": "0.01",
            "lot_size": "0.0001",
            "min_quantity": "5",
            "max_quantity": "5",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_market_status_requires_admin(client, admin_headers, user_headers):
    base = f"D{uuid.uuid4().hex[:6].upper()}"
    create = await client.post(
        "/api/v1/markets",
        json={
            "base_asset": base,
            "quote_asset": "USDT",
            "price_precision": 2,
            "quantity_precision": 4,
            "tick_size": "0.01",
            "lot_size": "0.0001",
            "min_quantity": "0.0001",
            "max_quantity": "100",
        },
        headers=admin_headers,
    )
    symbol = create.json()["symbol"]

    forbidden = await client.patch(
        f"/api/v1/markets/{symbol}/status", json={"status": "halted"}, headers=user_headers
    )
    assert forbidden.status_code == 403

    allowed = await client.patch(
        f"/api/v1/markets/{symbol}/status", json={"status": "halted"}, headers=admin_headers
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "halted"


@pytest.mark.asyncio
async def test_marketdata_404_for_unknown_symbol(client):
    resp = await client.get("/api/v1/marketdata/NOPE-USDT/ticker")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ticker_reflects_seeded_trades(client, db_session, event_bus, sample_market):
    state = await init_market_sim_state(db_session, sample_market, base_seed=1)
    for _ in range(3):
        await generate_next_trade(db_session, event_bus, sample_market, state)

    resp = await client.get(f"/api/v1/marketdata/{sample_market.symbol}/ticker")
    assert resp.status_code == 200
    body = resp.json()
    assert body["trade_count_24h"] == 3
    assert body["last_price"] is not None


@pytest.mark.asyncio
async def test_candles_endpoint_returns_folded_candles(client, db_session, sample_market):
    occurred_at = datetime.now(UTC)
    event = TradeEvent(
        event_id=str(uuid.uuid4()),
        market_id=str(sample_market.id),
        market_symbol=sample_market.symbol,
        sequence=1,
        price=Decimal("50.00"),
        quantity=Decimal("1.0"),
        side="buy",
        source="simulated",
        occurred_at=occurred_at,
    )
    await handle_trade_event(db_session, event.model_dump(mode="json"))

    resp = await client.get(f"/api/v1/marketdata/{sample_market.symbol}/candles?interval=1m")
    assert resp.status_code == 200
    candles = resp.json()
    assert len(candles) == 1
    assert candles[0]["close"] == "50.000000000000000000"


@pytest.mark.asyncio
async def test_trades_endpoint_returns_recent_trades_in_order(client, db_session, event_bus, sample_market):
    state = await init_market_sim_state(db_session, sample_market, base_seed=2)
    for _ in range(5):
        await generate_next_trade(db_session, event_bus, sample_market, state)

    resp = await client.get(f"/api/v1/marketdata/{sample_market.symbol}/trades?limit=10")
    assert resp.status_code == 200
    trades = resp.json()
    assert len(trades) == 5
    sequences = [t["sequence"] for t in trades]
    assert sequences == sorted(sequences)


@pytest.mark.asyncio
async def test_orderbook_endpoint_returns_latest_snapshot(client, db_session, event_bus, sample_market):
    import random

    await generate_snapshot(
        db_session, event_bus, sample_market, mid_price=Decimal("100.00"), rng=random.Random(1)
    )

    resp = await client.get(f"/api/v1/marketdata/{sample_market.symbol}/orderbook?depth=5")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["bids"]) <= 5
    assert len(body["asks"]) <= 5
    # Bids should be below asks (no crossed book).
    if body["bids"] and body["asks"]:
        assert Decimal(body["bids"][0][0]) < Decimal(body["asks"][0][0])


@pytest.mark.asyncio
async def test_orderbook_404_when_no_snapshot_yet(client, sample_market):
    resp = await client.get(f"/api/v1/marketdata/{sample_market.symbol}/orderbook")
    assert resp.status_code == 404
