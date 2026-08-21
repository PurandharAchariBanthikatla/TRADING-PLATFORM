"""Synthetic order book snapshots.

Same rationale as app/core/simulator.py: there is no real order book until
the matching engine exists (phase 4). This produces plausible depth around
the last trade price, on-tick, in the exact `[[price, quantity], ...]`
shape (bids highest-first, asks lowest-first) the matching engine will
need to produce -- so this is a producer swap in phase 4, not a contract
change for anything already consuming OrderBookSnapshot/OrderBookUpdateEvent.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import EventBus
from app.core.precision import round_to_lot, round_to_tick
from app.models.market import Market
from app.models.orderbook import OrderBookSnapshot
from app.schemas.events import OrderBookUpdateEvent, orderbook_stream_name

_DEPTH_LEVELS = 10


async def _next_sequence(db: AsyncSession, market_id) -> int:
    last = (
        await db.execute(
            select(OrderBookSnapshot)
            .where(OrderBookSnapshot.market_id == market_id)
            .order_by(OrderBookSnapshot.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return (last.sequence + 1) if last is not None else 1


def _build_levels(
    rng: random.Random, mid_price: Decimal, tick_size: Decimal, lot_size: Decimal, *, side: int
) -> list[list[Decimal]]:
    """side: -1 for bids (below mid), +1 for asks (above mid)."""
    levels = []
    price = mid_price
    for _i in range(_DEPTH_LEVELS):
        step = tick_size * Decimal(rng.randint(1, 3))
        price = round_to_tick(price + (side * step), tick_size)
        if price <= 0:
            break
        quantity = round_to_lot(Decimal(str(rng.uniform(0.1, 5.0))), lot_size) or lot_size
        levels.append([price, quantity])
    return levels


async def generate_snapshot(
    db: AsyncSession, event_bus: EventBus, market: Market, *, mid_price: Decimal, rng: random.Random
) -> OrderBookSnapshot:
    tick_size = Decimal(market.tick_size)
    lot_size = Decimal(market.lot_size)

    bids = _build_levels(rng, mid_price, tick_size, lot_size, side=-1)
    asks = _build_levels(rng, mid_price, tick_size, lot_size, side=1)

    sequence = await _next_sequence(db, market.id)
    snapshot_time = datetime.now(UTC)

    snapshot = OrderBookSnapshot(
        market_id=market.id,
        sequence=sequence,
        bids=[[str(p), str(q)] for p, q in bids],
        asks=[[str(p), str(q)] for p, q in asks],
        snapshot_time=snapshot_time,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    event = OrderBookUpdateEvent(
        event_id=str(uuid.uuid4()),
        market_id=str(market.id),
        market_symbol=market.symbol,
        sequence=sequence,
        bids=bids,
        asks=asks,
        snapshot_time=snapshot_time,
    )
    await event_bus.publish(orderbook_stream_name(market.symbol), event.model_dump(mode="json"))

    return snapshot
