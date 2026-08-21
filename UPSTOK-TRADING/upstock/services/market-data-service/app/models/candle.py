import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CandleInterval(str, enum.Enum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"

    @property
    def seconds(self) -> int:
        return {
            CandleInterval.ONE_MINUTE: 60,
            CandleInterval.FIVE_MINUTES: 300,
            CandleInterval.FIFTEEN_MINUTES: 900,
            CandleInterval.ONE_HOUR: 3600,
            CandleInterval.FOUR_HOURS: 14400,
            CandleInterval.ONE_DAY: 86400,
        }[self]


class Candle(Base):
    """One OHLCV bar. Built incrementally by app/core/candle_aggregator.py
    consuming the trade event stream -- see that module's docstring for how
    it stays correct under redelivery (idempotent consumption).
    """

    __tablename__ = "market_candles"

    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("markets.id", ondelete="RESTRICT"), nullable=False
    )
    interval: Mapped[CandleInterval] = mapped_column(
        SAEnum(
            CandleInterval, name="market_candle_interval", values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
    )
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    open: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)  # in base asset
    quote_volume: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # The sequence number of the last trade folded into this candle -- lets
    # the aggregator resume/verify correctly rather than re-deriving state
    # from a Redis consumer-group cursor alone.
    last_trade_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index(
            "ux_market_candles_market_interval_open_time", "market_id", "interval", "open_time", unique=True
        ),
    )
