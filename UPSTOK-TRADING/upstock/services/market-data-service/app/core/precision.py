"""Order-shape validation against a market's configuration.

This module has no FastAPI/DB dependencies on purpose -- it's pure
Decimal arithmetic over a Market's precision/tick/lot/min/max fields, so
Phase 4's matching engine can import and reuse it exactly as-is rather
than re-implementing (or subtly diverging from) the same rules.
"""

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from app.models.market import Market


class PrecisionViolationError(Exception):
    pass


@dataclass(frozen=True)
class OrderShape:
    price: Decimal
    quantity: Decimal


def round_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """Rounds down to the nearest valid tick. Rounding down (never up) for
    a price means a limit buy never executes worse than intended and a
    limit sell's rounding never manufactures a better price than quoted --
    the conservative direction for both sides.
    """
    return (price / tick_size).to_integral_value(rounding=ROUND_DOWN) * tick_size


def round_to_lot(quantity: Decimal, lot_size: Decimal) -> Decimal:
    return (quantity / lot_size).to_integral_value(rounding=ROUND_DOWN) * lot_size


def validate_order_shape(market: Market, *, price: Decimal, quantity: Decimal) -> OrderShape:
    """Raises PrecisionViolationError with a specific reason if the given
    price/quantity don't conform to `market`'s rules. Returns the validated
    (unchanged) shape on success -- this function never silently rounds a
    caller's input, it only accepts or rejects, so a caller that wants
    rounding must call round_to_tick/round_to_lot explicitly first and
    knowingly.
    """
    tick_size = Decimal(market.tick_size)
    lot_size = Decimal(market.lot_size)
    min_quantity = Decimal(market.min_quantity)
    max_quantity = Decimal(market.max_quantity)
    min_notional = Decimal(market.min_notional)

    if price <= 0:
        raise PrecisionViolationError("price must be > 0")
    if quantity <= 0:
        raise PrecisionViolationError("quantity must be > 0")

    if (price / tick_size) != (price / tick_size).to_integral_value():
        raise PrecisionViolationError(f"price {price} is not a multiple of tick_size {tick_size}")
    if (quantity / lot_size) != (quantity / lot_size).to_integral_value():
        raise PrecisionViolationError(f"quantity {quantity} is not a multiple of lot_size {lot_size}")

    if quantity < min_quantity:
        raise PrecisionViolationError(f"quantity {quantity} is below minimum {min_quantity}")
    if quantity > max_quantity:
        raise PrecisionViolationError(f"quantity {quantity} exceeds maximum {max_quantity}")

    notional = price * quantity
    if notional < min_notional:
        raise PrecisionViolationError(f"notional {notional} is below minimum {min_notional}")

    # Decimal-place limits (price_precision/quantity_precision) are not
    # separately enforced here: the tick/lot multiple checks above are the
    # more precise rule (e.g. tick_size=0.5 allows only even half-steps,
    # which a bare "<=N decimal places" check would wrongly accept 1.3
    # under). price_precision/quantity_precision on Market exist purely
    # for display formatting, not validation.

    return OrderShape(price=price, quantity=quantity)
