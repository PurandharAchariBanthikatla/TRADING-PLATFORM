"""Event envelopes published onto the event bus (app/core/event_bus.py).

Every event carries `event_version`. A consumer encountering a version
higher than it knows how to handle should dead-letter the event rather
than guess at its shape -- see CandleAggregator.handle_trade_event for the
concrete check. Bumping a field's meaning (not just adding an optional
field) should bump the version.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


def trade_stream_name(market_symbol: str) -> str:
    return f"marketdata.trades.{market_symbol}"


def candle_stream_name(market_symbol: str) -> str:
    return f"marketdata.candles.{market_symbol}"


def orderbook_stream_name(market_symbol: str) -> str:
    return f"marketdata.orderbook.{market_symbol}"


class TradeEvent(BaseModel):
    event_version: int = 1
    event_id: str  # UUID; used by consumers for their own dedup bookkeeping
    market_id: str
    market_symbol: str
    sequence: int
    price: Decimal
    quantity: Decimal
    side: str
    source: str
    occurred_at: datetime


class CandleUpdateEvent(BaseModel):
    event_version: int = 1
    event_id: str
    market_id: str
    market_symbol: str
    interval: str
    open_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    is_closed: bool = Field(description="True once open_time + interval has fully elapsed")


class OrderBookUpdateEvent(BaseModel):
    event_version: int = 1
    event_id: str
    market_id: str
    market_symbol: str
    sequence: int
    bids: list[list[Decimal]]
    asks: list[list[Decimal]]
    snapshot_time: datetime
