"""Background asyncio tasks wired up in main.py's lifespan.

Three loops, each with its own DB session per iteration (never one session
held open across an indefinite sleep) and all sharing one EventBus/Redis
connection:

  - producer_loop: for every active (status=TRADING) market, generates one
    synthetic trade and one order-book snapshot per tick, via
    app.core.simulator / app.core.orderbook_simulator. This is the phase-3
    stand-in data source described in those modules' docstrings.
  - candle_consumer_loop: reads new trade events off each active market's
    stream via a Redis Streams consumer group, folds them into candles
    (idempotently -- see candle_aggregator.py), acks on success, and
    publishes CandleUpdateEvents.
  - dlq_maintenance_loop: periodically reclaims stale-pending messages and
    moves repeatedly-failed ones to the dead-letter stream (see
    event_bus.claim_stale_and_deadletter).

These run as three separate tasks (not one loop doing everything) so a
slow/stuck consumer never blocks the producer, matching how a real
Kafka/Redpanda deployment would also run producer and consumer as
independent processes.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.core.candle_aggregator import (
    UnsupportedEventVersionError,
    handle_trade_event,
    publish_candle_updates,
)
from app.core.config import settings
from app.core.event_bus import EventBus
from app.core.logging import get_logger
from app.core.orderbook_simulator import generate_snapshot
from app.core.simulator import MarketSimState, generate_next_trade, init_market_sim_state
from app.db.session import AsyncSessionLocal
from app.models.market import Market, MarketStatus
from app.schemas.events import trade_stream_name

log = get_logger(__name__)

CANDLE_CONSUMER_GROUP = "candle-aggregator"


async def _active_markets() -> list[Market]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Market).where(Market.status == MarketStatus.TRADING))
        return list(result.scalars().all())


async def producer_loop(event_bus: EventBus, stop_event: asyncio.Event) -> None:
    sim_states: dict[str, MarketSimState] = {}

    while not stop_event.is_set():
        try:
            markets = await _active_markets()
            for market in markets:
                async with AsyncSessionLocal() as db:
                    market_key = str(market.id)
                    if market_key not in sim_states:
                        sim_states[market_key] = await init_market_sim_state(
                            db, market, settings.SIMULATOR_SEED
                        )
                    state = sim_states[market_key]

                    trade = await generate_next_trade(db, event_bus, market, state)
                    await generate_snapshot(
                        db, event_bus, market, mid_price=Decimal(trade.price), rng=state.rng
                    )
        except Exception:
            log.error("producer_loop_error", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.SIMULATOR_TICK_INTERVAL_SECONDS)
        except TimeoutError:
            pass


async def candle_consumer_loop(event_bus: EventBus, stop_event: asyncio.Event) -> None:
    consumer_name = "candle-aggregator-1"
    known_streams: set[str] = set()

    while not stop_event.is_set():
        try:
            markets = await _active_markets()
            for market in markets:
                stream = trade_stream_name(market.symbol)
                if stream not in known_streams:
                    await event_bus.ensure_group(stream, CANDLE_CONSUMER_GROUP)
                    known_streams.add(stream)

                messages = await event_bus.consume_group(
                    stream, CANDLE_CONSUMER_GROUP, consumer_name, count=50, block_ms=200
                )
                for message in messages:
                    async with AsyncSessionLocal() as db:
                        try:
                            touched = await handle_trade_event(db, message.fields)
                            await publish_candle_updates(event_bus, market.symbol, touched)
                            await event_bus.ack(stream, CANDLE_CONSUMER_GROUP, message.id)
                        except UnsupportedEventVersionError:
                            log.error(
                                "candle_consumer_unsupported_event_version",
                                stream=stream,
                                message_id=message.id,
                            )
                            # Deliberately not acked -- left pending so the
                            # DLQ maintenance loop moves it to the dead
                            # letter stream after enough failed attempts,
                            # rather than silently dropping it here.
        except Exception:
            log.error("candle_consumer_loop_error", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.5)
        except TimeoutError:
            pass


async def dlq_maintenance_loop(event_bus: EventBus, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            markets = await _active_markets()
            for market in markets:
                stream = trade_stream_name(market.symbol)
                await event_bus.claim_stale_and_deadletter(stream, CANDLE_CONSUMER_GROUP, "dlq-sweeper")
        except Exception:
            log.error("dlq_maintenance_loop_error", exc_info=True)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=10.0)
        except TimeoutError:
            pass
