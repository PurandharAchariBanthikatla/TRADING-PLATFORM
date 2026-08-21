"""Paper/sandbox market-data generation.

Phase 3 has no matching engine (that's phase 4), so there is no real
source of trades yet. This module generates synthetic-but-realistic
trades through the *same* pipeline real trades will eventually use
(persist to Postgres, publish to the event bus) so downstream consumers
(candle aggregation, ticker calculation, the future WebSocket gateway)
are exercised against a real backend data path -- not frontend-mocked
data, per the phase's explicit requirement.

Determinism: each market gets its own `random.Random` seeded from
`(SIMULATOR_SEED, market.symbol)`, so a given seed always produces the
same sequence of trades for a given market regardless of what other
markets are also running -- this is what makes
test_simulator_is_deterministic meaningful.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_bus import EventBus
from app.core.precision import round_to_lot, round_to_tick
from app.models.market import Market
from app.models.trade import Trade, TradeSide, TradeSource
from app.schemas.events import TradeEvent, trade_stream_name

# Per-tick price volatility, as a fraction of price. Deliberately modest --
# this only needs to look like a plausible walking price for demoing/
# testing the pipeline, not to model real market microstructure.
_PRICE_VOLATILITY = Decimal("0.0015")


@dataclass
class MarketSimState:
    rng: random.Random
    last_price: Decimal
    last_sequence: int


def _seed_for_market(base_seed: int, market_symbol: str) -> int:
    return base_seed ^ (hash(market_symbol) & 0xFFFFFFFF)


async def init_market_sim_state(db: AsyncSession, market: Market, base_seed: int) -> MarketSimState:
    """Resumes from the last persisted trade's price/sequence if this
    market already has trade history (e.g. service restart), otherwise
    starts from a seed price derived from tick_size so it's always a
    valid, on-tick starting point.
    """
    last_trade = (
        await db.execute(
            select(Trade).where(Trade.market_id == market.id).order_by(Trade.sequence.desc()).limit(1)
        )
    ).scalar_one_or_none()

    rng = random.Random(_seed_for_market(base_seed, market.symbol))

    if last_trade is not None:
        return MarketSimState(
            rng=rng, last_price=Decimal(last_trade.price), last_sequence=last_trade.sequence
        )

    tick = Decimal(market.tick_size)
    seed_price = round_to_tick(tick * Decimal(10_000), tick)
    return MarketSimState(rng=rng, last_price=seed_price, last_sequence=0)


async def generate_next_trade(
    db: AsyncSession, event_bus: EventBus, market: Market, state: MarketSimState
) -> Trade:
    """Advances `state` in place, persists one Trade row, and publishes the
    corresponding TradeEvent. Returns the persisted Trade.
    """
    tick_size = Decimal(market.tick_size)
    lot_size = Decimal(market.lot_size)

    pct_change = Decimal(str(state.rng.gauss(0, float(_PRICE_VOLATILITY))))
    candidate_price = state.last_price * (Decimal(1) + pct_change)
    new_price = round_to_tick(candidate_price, tick_size)
    if new_price <= 0:
        new_price = tick_size  # floor: never let the walk hit zero or negative

    raw_quantity = Decimal(
        str(state.rng.uniform(float(market.min_quantity), float(market.min_quantity) * 20))
    )
    quantity = round_to_lot(raw_quantity, lot_size)
    if quantity < Decimal(market.min_quantity):
        quantity = round_to_lot(Decimal(market.min_quantity), lot_size) or lot_size

    # The simulator's own generated trades must themselves be valid orders
    # for this market, including satisfying min_notional. A random walk
    # over [min_quantity, min_quantity*20] can easily fall short of
    # min_notional when price is small relative to it, so bump quantity up
    # (never down) to clear the floor, then re-clamp to max_quantity.
    #
    # NOTE: deliberately NOT using Decimal.quantize(lot_size, ...) here --
    # quantize() rounds to match its argument's *exponent* (decimal place
    # count), not to multiples of its *value*. lot_size loaded from a
    # NUMERIC(38,18) column carries an 18-decimal-place exponent, so
    # quantize(lot_size) would round to 18 decimal places, not to actual
    # lot_size multiples. Integer ceiling division is what's actually needed.
    min_notional = Decimal(market.min_notional)
    if min_notional > 0 and (new_price * quantity) < min_notional:
        units_needed = (min_notional / new_price / lot_size).to_integral_value(rounding=ROUND_CEILING)
        quantity = units_needed * lot_size

    if quantity > Decimal(market.max_quantity):
        quantity = round_to_lot(Decimal(market.max_quantity), lot_size)

    side = TradeSide.BUY if state.rng.random() < 0.5 else TradeSide.SELL
    occurred_at = datetime.now(UTC)
    next_sequence = state.last_sequence + 1

    trade = Trade(
        market_id=market.id,
        sequence=next_sequence,
        price=new_price,
        quantity=quantity,
        side=side,
        source=TradeSource.SIMULATED,
        occurred_at=occurred_at,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)

    state.last_price = new_price
    state.last_sequence = next_sequence

    event = TradeEvent(
        event_id=str(uuid.uuid4()),
        market_id=str(market.id),
        market_symbol=market.symbol,
        sequence=next_sequence,
        price=new_price,
        quantity=quantity,
        side=side.value,
        source=TradeSource.SIMULATED.value,
        occurred_at=occurred_at,
    )
    await event_bus.publish(trade_stream_name(market.symbol), event.model_dump(mode="json"))

    return trade
