import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.candle_aggregator import UnsupportedEventVersionError, floor_to_interval, handle_trade_event
from app.models.candle import Candle, CandleInterval
from app.schemas.events import TradeEvent


def _trade_event(market_id: str, sequence: int, price: str, quantity: str, occurred_at: datetime) -> dict:
    event = TradeEvent(
        event_id=str(uuid.uuid4()),
        market_id=market_id,
        market_symbol="TEST-USDT",
        sequence=sequence,
        price=Decimal(price),
        quantity=Decimal(quantity),
        side="buy",
        source="simulated",
        occurred_at=occurred_at,
    )
    return event.model_dump(mode="json")


def test_floor_to_interval():
    ts = datetime(2026, 1, 1, 12, 34, 56, tzinfo=UTC)
    assert floor_to_interval(ts, CandleInterval.ONE_MINUTE) == datetime(2026, 1, 1, 12, 34, 0, tzinfo=UTC)
    assert floor_to_interval(ts, CandleInterval.ONE_HOUR) == datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_single_trade_creates_candle_on_every_interval(db_session, sample_market):
    occurred_at = datetime.now(UTC)
    event = _trade_event(str(sample_market.id), 1, "100.00", "0.5", occurred_at)

    touched = await handle_trade_event(db_session, event)

    assert len(touched) == len(CandleInterval)
    for candle in touched:
        assert Decimal(candle.open) == Decimal("100.00")
        assert Decimal(candle.high) == Decimal("100.00")
        assert Decimal(candle.low) == Decimal("100.00")
        assert Decimal(candle.close) == Decimal("100.00")
        assert Decimal(candle.volume) == Decimal("0.5")
        assert candle.trade_count == 1


@pytest.mark.asyncio
async def test_second_trade_updates_high_low_close_and_accumulates_volume(db_session, sample_market):
    occurred_at = datetime.now(UTC)
    await handle_trade_event(db_session, _trade_event(str(sample_market.id), 1, "100.00", "1.0", occurred_at))
    await handle_trade_event(db_session, _trade_event(str(sample_market.id), 2, "105.00", "2.0", occurred_at))
    touched = await handle_trade_event(
        db_session, _trade_event(str(sample_market.id), 3, "95.00", "0.5", occurred_at)
    )

    one_min = next(c for c in touched if c.interval == CandleInterval.ONE_MINUTE)
    assert Decimal(one_min.open) == Decimal("100.00")
    assert Decimal(one_min.high) == Decimal("105.00")
    assert Decimal(one_min.low) == Decimal("95.00")
    assert Decimal(one_min.close) == Decimal("95.00")
    assert Decimal(one_min.volume) == Decimal("3.5")
    assert one_min.trade_count == 3


@pytest.mark.asyncio
async def test_redelivered_event_is_a_no_op(db_session, sample_market):
    """The core idempotency guarantee: processing the exact same event
    twice (simulating at-least-once redelivery from the consumer group)
    must not double-count volume or trade_count.
    """
    occurred_at = datetime.now(UTC)
    event = _trade_event(str(sample_market.id), 1, "100.00", "1.0", occurred_at)

    first_touched = await handle_trade_event(db_session, event)
    second_touched = await handle_trade_event(db_session, event)

    assert len(first_touched) == len(CandleInterval)
    assert len(second_touched) == 0  # fully a no-op

    result = await db_session.execute(
        select(Candle).where(
            Candle.market_id == sample_market.id, Candle.interval == CandleInterval.ONE_MINUTE
        )
    )
    candle = result.scalar_one()
    assert Decimal(candle.volume) == Decimal("1.0")  # not 2.0
    assert candle.trade_count == 1  # not 2


@pytest.mark.asyncio
async def test_out_of_order_redelivery_of_earlier_sequence_is_also_a_no_op(db_session, sample_market):
    occurred_at = datetime.now(UTC)
    await handle_trade_event(db_session, _trade_event(str(sample_market.id), 1, "100.00", "1.0", occurred_at))
    await handle_trade_event(db_session, _trade_event(str(sample_market.id), 2, "101.00", "1.0", occurred_at))

    # Redeliver sequence 1 again, after 2 has already been applied.
    touched = await handle_trade_event(
        db_session, _trade_event(str(sample_market.id), 1, "100.00", "1.0", occurred_at)
    )
    assert touched == []

    result = await db_session.execute(
        select(Candle).where(
            Candle.market_id == sample_market.id, Candle.interval == CandleInterval.ONE_MINUTE
        )
    )
    candle = result.scalar_one()
    assert candle.trade_count == 2
    assert Decimal(candle.volume) == Decimal("2.0")


@pytest.mark.asyncio
async def test_unsupported_event_version_raises(db_session, sample_market):
    event = _trade_event(str(sample_market.id), 1, "100.00", "1.0", datetime.now(UTC))
    event["event_version"] = 999

    with pytest.raises(UnsupportedEventVersionError):
        await handle_trade_event(db_session, event)


@pytest.mark.asyncio
async def test_trades_in_different_minutes_create_separate_candles(db_session, sample_market):
    from datetime import timedelta

    t1 = datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC)
    t2 = t1 + timedelta(minutes=1)

    await handle_trade_event(db_session, _trade_event(str(sample_market.id), 1, "100.00", "1.0", t1))
    await handle_trade_event(db_session, _trade_event(str(sample_market.id), 2, "110.00", "1.0", t2))

    result = await db_session.execute(
        select(Candle)
        .where(Candle.market_id == sample_market.id, Candle.interval == CandleInterval.ONE_MINUTE)
        .order_by(Candle.open_time)
    )
    candles = list(result.scalars().all())
    assert len(candles) == 2
    assert Decimal(candles[0].close) == Decimal("100.00")
    assert Decimal(candles[1].close) == Decimal("110.00")
