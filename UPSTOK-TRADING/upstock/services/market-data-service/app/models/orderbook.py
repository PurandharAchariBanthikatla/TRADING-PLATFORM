import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderBookSnapshot(Base):
    """A point-in-time order book snapshot. In phase 3 this is produced by
    app/core/orderbook_simulator.py (synthetic levels around the last
    trade price, respecting the market's tick_size) -- there is no real
    order book until the matching engine (phase 4) exists. The `bids` and
    `asks` shape ([[price, quantity], ...], best-first) is chosen now to
    match what the matching engine will need to produce, so phase 4 is a
    change of producer, not a change of contract or of anything consuming
    this table.
    """

    __tablename__ = "market_orderbook_snapshots"

    market_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("markets.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(nullable=False)  # per-market monotonic snapshot sequence
    bids: Mapped[list] = mapped_column(JSONB, nullable=False)  # [[price, qty], ...] highest first
    asks: Mapped[list] = mapped_column(JSONB, nullable=False)  # [[price, qty], ...] lowest first
    snapshot_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ux_orderbook_snapshots_market_sequence", "market_id", "sequence", unique=True),)
