"""Consumes trade events and folds them into OHLCV candles.

**Idempotency under redelivery** is the property this module exists to
get right: Redis Streams consumer groups guarantee *at-least-once*
delivery, not exactly-once (a consumer that crashes after processing but
before XACK will have its message reclaimed and redelivered -- see
event_bus.claim_stale_and_deadletter). handle_trade_event() must therefore
be safe to call twice with the identical event: it checks each candle's
`last_trade_sequence` before folding a trade in, and no-ops if that
trade's sequence has already been applied to that candle. Trade sequences
are monotonic per market, so "sequence <= last_trade_sequence" is a
correct and sufficient dedup check without needing a separate
processed-event-ids set.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import EventBus
from app.core.logging import get_logger
from app.models.candle import Candle, CandleInterval
from app.schemas.events import CandleUpdateEvent, TradeEvent, candle_stream_name

log = get_logger(__name__)

SUPPORTED_TRADE_EVENT_VERSIONS = {1}


class UnsupportedEventVersionError(Exception):
    """Raised when an event's `event_version` is higher than this consumer
    knows how to handle. Callers should dead-letter rather than skip
    silently -- an unknown version might change field meaning, not just
    add optional fields, and guessing at it risks corrupting a candle.
    """


def floor_to_interval(ts: datetime, interval: CandleInterval) -> datetime:
    epoch_seconds = int(ts.timestamp())
    floored = epoch_seconds - (epoch_seconds % interval.seconds)
    return datetime.fromtimestamp(floored, tz=UTC)


async def _upsert_one_candle(db: AsyncSession, event: TradeEvent, interval: CandleInterval) -> Candle | None:
    open_time = floor_to_interval(event.occurred_at, interval)

    existing = (
        await db.execute(
            select(Candle).where(
                Candle.market_id == event.market_id,
                Candle.interval == interval,
                Candle.open_time == open_time,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        if event.sequence <= existing.last_trade_sequence:
            # Already applied -- redelivery, not new data. No-op.
            return None
        existing.high = max(Decimal(existing.high), event.price)
        existing.low = min(Decimal(existing.low), event.price)
        existing.close = event.price
        existing.volume = Decimal(existing.volume) + event.quantity
        existing.quote_volume = Decimal(existing.quote_volume) + (event.price * event.quantity)
        existing.trade_count += 1
        existing.last_trade_sequence = event.sequence
        candle = existing
    else:
        candle = Candle(
            market_id=event.market_id,
            interval=interval,
            open_time=open_time,
            open=event.price,
            high=event.price,
            low=event.price,
            close=event.price,
            volume=event.quantity,
            quote_volume=event.price * event.quantity,
            trade_count=1,
            last_trade_sequence=event.sequence,
        )
        db.add(candle)

    return candle


async def handle_trade_event(db: AsyncSession, raw_event: dict) -> list[Candle]:
    """Folds one trade event into every candle interval. Safe to call
    repeatedly with the same event (see module docstring). Returns the
    candles that were actually modified (empty list on a pure redelivery
    no-op).
    """
    if raw_event.get("event_version") not in SUPPORTED_TRADE_EVENT_VERSIONS:
        raise UnsupportedEventVersionError(f"unsupported event_version: {raw_event.get('event_version')}")

    event = TradeEvent.model_validate(raw_event)

    touched: list[Candle] = []
    for interval in CandleInterval:
        candle = await _upsert_one_candle(db, event, interval)
        if candle is not None:
            touched.append(candle)

    await db.commit()
    for candle in touched:
        await db.refresh(candle)

    return touched


async def publish_candle_updates(event_bus: EventBus, market_symbol: str, candles: list[Candle]) -> None:
    now = datetime.now(UTC)
    for candle in candles:
        is_closed = now >= (candle.open_time + timedelta(seconds=candle.interval.seconds))
        event = CandleUpdateEvent(
            event_id=str(uuid.uuid4()),
            market_id=str(candle.market_id),
            market_symbol=market_symbol,
            interval=candle.interval.value,
            open_time=candle.open_time,
            open=Decimal(candle.open),
            high=Decimal(candle.high),
            low=Decimal(candle.low),
            close=Decimal(candle.close),
            volume=Decimal(candle.volume),
            quote_volume=Decimal(candle.quote_volume),
            trade_count=candle.trade_count,
            is_closed=is_closed,
        )
        await event_bus.publish(candle_stream_name(market_symbol), event.model_dump(mode="json"))
