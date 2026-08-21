import enum
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketStatus(str, enum.Enum):
    TRADING = "trading"
    HALTED = "halted"  # temporarily paused (e.g. by an admin); resumable
    DELISTED = "delisted"  # permanently removed from trading


class Market(Base):
    """A tradeable (base_asset, quote_asset) pair, e.g. BTC/USDT, and every
    piece of configuration that governs how orders against it must be
    shaped. This table is what the matching engine (phase 4) will validate
    every order against -- precision, tick/lot size, min/max quantity --
    so its correctness now matters beyond just display formatting.
    """

    __tablename__ = "markets"

    symbol: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)  # "BTC-USDT"
    base_asset: Mapped[str] = mapped_column(String(20), nullable=False)
    quote_asset: Mapped[str] = mapped_column(String(20), nullable=False)

    status: Mapped[MarketStatus] = mapped_column(
        SAEnum(MarketStatus, name="market_status", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=MarketStatus.TRADING,
    )

    # Number of decimal places a price/quantity may be expressed in. Used
    # for display and as the basis tick_size/lot_size are defined against.
    price_precision: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_precision: Mapped[int] = mapped_column(Integer, nullable=False)

    # Smallest allowed increment. A valid price must be an exact multiple
    # of tick_size; a valid quantity an exact multiple of lot_size. See
    # app/core/precision.py for the validation these values feed into.
    tick_size: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    lot_size: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)

    min_quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    max_quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    min_notional: Mapped[Decimal] = mapped_column(
        Numeric(38, 18), nullable=False, default=0
    )  # min price*quantity allowed, in quote_asset

    maker_fee_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=10)  # 10 bps = 0.10%
    taker_fee_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=15)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("tick_size > 0", name="ck_markets_tick_size_positive"),
        CheckConstraint("lot_size > 0", name="ck_markets_lot_size_positive"),
        CheckConstraint("min_quantity > 0", name="ck_markets_min_quantity_positive"),
        CheckConstraint("max_quantity > min_quantity", name="ck_markets_max_gt_min_quantity"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Market {self.symbol} status={self.status.value}>"
