import random
from decimal import Decimal

import pytest

from app.core.precision import round_to_tick, validate_order_shape
from app.core.simulator import MarketSimState, _seed_for_market, generate_next_trade, init_market_sim_state
from app.schemas.events import trade_stream_name


def test_seed_derivation_is_a_pure_function_of_seed_and_symbol():
    a = random.Random(_seed_for_market(42, "BTC-USDT"))
    b = random.Random(_seed_for_market(42, "BTC-USDT"))
    assert [a.random() for _ in range(10)] == [b.random() for _ in range(10)]


def test_seed_derivation_differs_across_symbols():
    a = random.Random(_seed_for_market(42, "BTC-USDT"))
    b = random.Random(_seed_for_market(42, "ETH-USDT"))
    assert [a.random() for _ in range(10)] != [b.random() for _ in range(10)]


@pytest.mark.asyncio
async def test_generate_next_trade_matches_the_deterministic_walk_formula(
    db_session, event_bus, sample_market
):
    """generate_next_trade's price must be a pure function of the RNG draw
    it consumes -- replaying the exact same arithmetic independently, with
    an independently-seeded RNG, must produce the identical next price.
    """
    tick = Decimal(sample_market.tick_size)
    seed_price = round_to_tick(tick * Decimal(10_000), tick)

    state = MarketSimState(
        rng=random.Random(_seed_for_market(777, sample_market.symbol)), last_price=seed_price, last_sequence=0
    )
    trade = await generate_next_trade(db_session, event_bus, sample_market, state)

    independent_rng = random.Random(_seed_for_market(777, sample_market.symbol))
    pct_change = Decimal(str(independent_rng.gauss(0, float(Decimal("0.0015")))))
    expected_price = round_to_tick(seed_price * (Decimal(1) + pct_change), tick)
    if expected_price <= 0:
        expected_price = tick

    assert Decimal(trade.price) == expected_price


@pytest.mark.asyncio
async def test_generated_trades_respect_market_precision(db_session, event_bus, sample_market):
    state = await init_market_sim_state(db_session, sample_market, base_seed=99)
    for _ in range(20):
        trade = await generate_next_trade(db_session, event_bus, sample_market, state)
        # Must not raise -- every generated trade is a valid order shape.
        validate_order_shape(sample_market, price=Decimal(trade.price), quantity=Decimal(trade.quantity))


@pytest.mark.asyncio
async def test_generate_next_trade_publishes_to_event_bus(db_session, event_bus, sample_market, redis_client):
    state = await init_market_sim_state(db_session, sample_market, base_seed=5)
    await generate_next_trade(db_session, event_bus, sample_market, state)

    stream = trade_stream_name(sample_market.symbol)
    length = await redis_client.xlen(stream)
    assert length == 1


@pytest.mark.asyncio
async def test_sequence_increments_and_persists(db_session, event_bus, sample_market):
    state = await init_market_sim_state(db_session, sample_market, base_seed=1)
    t1 = await generate_next_trade(db_session, event_bus, sample_market, state)
    t2 = await generate_next_trade(db_session, event_bus, sample_market, state)
    assert t2.sequence == t1.sequence + 1


@pytest.mark.asyncio
async def test_resumes_from_last_persisted_trade(db_session, event_bus, sample_market):
    state = await init_market_sim_state(db_session, sample_market, base_seed=1)
    last_trade = await generate_next_trade(db_session, event_bus, sample_market, state)

    resumed_state = await init_market_sim_state(db_session, sample_market, base_seed=1)
    assert resumed_state.last_sequence == last_trade.sequence
    assert resumed_state.last_price == Decimal(last_trade.price)
