from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, field_validator

from app.models.market import MarketStatus

# See ledger-service/app/schemas/ledger.py: SQLAlchemy returns uuid.UUID
# objects for UUID columns; Pydantic v2's `str` type won't implicitly
# coerce them.
UUIDStr = Annotated[str, BeforeValidator(lambda v: str(v) if v is not None else v)]


class AssetCreateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    decimals: int = Field(default=8, ge=0, le=18)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class AssetResponse(BaseModel):
    id: UUIDStr
    symbol: str
    name: str
    decimals: int
    is_active: bool

    model_config = {"from_attributes": True}


class MarketCreateRequest(BaseModel):
    base_asset: str = Field(min_length=1, max_length=20)
    quote_asset: str = Field(min_length=1, max_length=20)
    price_precision: int = Field(ge=0, le=18)
    quantity_precision: int = Field(ge=0, le=18)
    tick_size: Decimal = Field(gt=0)
    lot_size: Decimal = Field(gt=0)
    min_quantity: Decimal = Field(gt=0)
    max_quantity: Decimal = Field(gt=0)
    min_notional: Decimal = Field(default=Decimal(0), ge=0)
    maker_fee_bps: int = Field(default=10, ge=0, le=1000)
    taker_fee_bps: int = Field(default=15, ge=0, le=1000)

    @field_validator("base_asset", "quote_asset")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class MarketStatusUpdateRequest(BaseModel):
    status: MarketStatus


class MarketResponse(BaseModel):
    id: UUIDStr
    symbol: str
    base_asset: str
    quote_asset: str
    status: MarketStatus
    price_precision: int
    quantity_precision: int
    tick_size: Decimal
    lot_size: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal
    maker_fee_bps: int
    taker_fee_bps: int
    is_active: bool

    model_config = {"from_attributes": True}


class TickerResponse(BaseModel):
    market_id: UUIDStr
    symbol: str
    last_price: Decimal | None
    open_24h: Decimal | None
    high_24h: Decimal | None
    low_24h: Decimal | None
    volume_24h: Decimal
    quote_volume_24h: Decimal
    trade_count_24h: int
    change_24h_pct: Decimal | None


class CandleResponse(BaseModel):
    open_time: datetime
    interval: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int

    model_config = {"from_attributes": True}


class TradeResponse(BaseModel):
    sequence: int
    price: Decimal
    quantity: Decimal
    side: str
    occurred_at: datetime

    model_config = {"from_attributes": True}


class OrderBookResponse(BaseModel):
    sequence: int
    bids: list[list[Decimal]]
    asks: list[list[Decimal]]
    snapshot_time: datetime

    model_config = {"from_attributes": True}
