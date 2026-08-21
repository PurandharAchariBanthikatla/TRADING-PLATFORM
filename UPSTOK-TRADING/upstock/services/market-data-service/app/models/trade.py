import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TradeSide(str, enum.Enum):
    BUY = "buy"  # taker side
    SELL = "sell"


class TradeSource(str, enum.Enum):
    # Phase 3 has no matching engine yet, so every Trade row today comes
    # from app/core/simulator.py -- a deterministic paper-data generator,
    # not a real execution. This column exists so that distinction is
    # explicit in the data itself (queryable, auditable) rather than
    # inferred, and so Phase 4 can start writing MATCHING_ENGINE rows into
    # the exact same table/pipeline without a schema change.
    SIMULATED = "simulated"
    MATCHING_ENGINE = "matching_engine"


class Trade(Base):
    __tablename__ = "market_trades"

    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("markets.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(nullable=False)  # per-market monotonic trade sequence
    price: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    side: Mapped[TradeSide] = mapped_column(
        SAEnum(TradeSide, name="market_trade_side", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
    )
    source: Mapped[TradeSource] = mapped_column(
        SAEnum(TradeSource, name="market_trade_source", values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=TradeSource.SIMULATED,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ux_market_trades_market_sequence", "market_id", "sequence", unique=True),
        Index("ix_market_trades_market_occurred_at", "market_id", "occurred_at"),
    )
