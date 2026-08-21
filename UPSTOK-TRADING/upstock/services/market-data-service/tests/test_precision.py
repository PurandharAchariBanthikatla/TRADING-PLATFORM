from decimal import Decimal

import pytest

from app.core.precision import PrecisionViolationError, round_to_lot, round_to_tick, validate_order_shape
from app.models.market import Market, MarketStatus


def _market(**overrides) -> Market:
    defaults = dict(
        symbol="BTC-USDT",
        base_asset="BTC",
        quote_asset="USDT",
        status=MarketStatus.TRADING,
        price_precision=2,
        quantity_precision=4,
        tick_size=Decimal("0.5"),
        lot_size=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("10"),
        min_notional=Decimal("10"),
        maker_fee_bps=10,
        taker_fee_bps=15,
    )
    defaults.update(overrides)
    return Market(**defaults)


def test_round_to_tick_rounds_down():
    assert round_to_tick(Decimal("100.7"), Decimal("0.5")) == Decimal("100.5")
    assert round_to_tick(Decimal("100.5"), Decimal("0.5")) == Decimal("100.5")


def test_round_to_lot_rounds_down():
    assert round_to_lot(Decimal("1.2345"), Decimal("0.001")) == Decimal("1.234")


def test_valid_order_shape_passes():
    market = _market()
    shape = validate_order_shape(market, price=Decimal("100.5"), quantity=Decimal("0.1"))
    assert shape.price == Decimal("100.5")
    assert shape.quantity == Decimal("0.1")


def test_price_not_multiple_of_tick_is_rejected():
    market = _market()
    with pytest.raises(PrecisionViolationError, match="tick_size"):
        validate_order_shape(market, price=Decimal("100.3"), quantity=Decimal("0.1"))


def test_quantity_not_multiple_of_lot_is_rejected():
    market = _market()
    with pytest.raises(PrecisionViolationError, match="lot_size"):
        validate_order_shape(market, price=Decimal("100.5"), quantity=Decimal("0.10005"))


def test_quantity_below_minimum_is_rejected():
    market = _market(min_quantity=Decimal("0.005"), lot_size=Decimal("0.001"))
    with pytest.raises(PrecisionViolationError, match="minimum"):
        validate_order_shape(market, price=Decimal("100.5"), quantity=Decimal("0.002"))


def test_quantity_above_maximum_is_rejected():
    market = _market()
    with pytest.raises(PrecisionViolationError, match="maximum"):
        validate_order_shape(market, price=Decimal("100.5"), quantity=Decimal("11"))


def test_notional_below_minimum_is_rejected():
    market = _market(min_notional=Decimal("1000"))
    with pytest.raises(PrecisionViolationError, match="notional"):
        validate_order_shape(market, price=Decimal("100.5"), quantity=Decimal("0.1"))


def test_zero_or_negative_price_rejected():
    market = _market()
    with pytest.raises(PrecisionViolationError):
        validate_order_shape(market, price=Decimal("0"), quantity=Decimal("0.1"))
