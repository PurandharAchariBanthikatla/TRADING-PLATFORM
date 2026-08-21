"""24-hour ticker statistics.

Postgres (the `market_trades` table) is the source of truth; this module
only computes a rolling 24h aggregate from it and caches the result in
Redis for a short TTL (TICKER_CACHE_TTL_SECONDS) so a busy ticker endpoint
doesn't re-scan trade history on every request. The cache is purely a
performance layer -- deleting it changes nothing but latency, never
correctness, which is the same principle ledger-service and wallet-service
apply to what belongs in Postgres vs. Redis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import redis.asyncio as redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.trade import Trade


@dataclass(frozen=True)
class TickerSnapshot:
    market_id: str
    last_price: Decimal | None
    open_24h: Decimal | None
    high_24h: Decimal | None
    low_24h: Decimal | None
    volume_24h: Decimal
    quote_volume_24h: Decimal
    trade_count_24h: int
    change_24h_pct: Decimal | None

    def to_cache_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "last_price": str(self.last_price) if self.last_price is not None else None,
            "open_24h": str(self.open_24h) if self.open_24h is not None else None,
            "high_24h": str(self.high_24h) if self.high_24h is not None else None,
            "low_24h": str(self.low_24h) if self.low_24h is not None else None,
            "volume_24h": str(self.volume_24h),
            "quote_volume_24h": str(self.quote_volume_24h),
            "trade_count_24h": self.trade_count_24h,
            "change_24h_pct": str(self.change_24h_pct) if self.change_24h_pct is not None else None,
        }

    @classmethod
    def from_cache_dict(cls, d: dict) -> TickerSnapshot:
        def _dec(v):
            return Decimal(v) if v is not None else None

        return cls(
            market_id=d["market_id"],
            last_price=_dec(d["last_price"]),
            open_24h=_dec(d["open_24h"]),
            high_24h=_dec(d["high_24h"]),
            low_24h=_dec(d["low_24h"]),
            volume_24h=Decimal(d["volume_24h"]),
            quote_volume_24h=Decimal(d["quote_volume_24h"]),
            trade_count_24h=d["trade_count_24h"],
            change_24h_pct=_dec(d["change_24h_pct"]),
        )


def _cache_key(market_id: str) -> str:
    return f"ticker:{market_id}"


async def compute_ticker(db: AsyncSession, market_id: str) -> TickerSnapshot:
    since = datetime.now(UTC) - timedelta(hours=24)

    row = (
        await db.execute(
            select(
                func.max(Trade.price),
                func.min(Trade.price),
                func.sum(Trade.quantity),
                func.sum(Trade.price * Trade.quantity),
                func.count(Trade.id),
            ).where(Trade.market_id == market_id, Trade.occurred_at >= since)
        )
    ).one()
    high_24h, low_24h, volume_24h, quote_volume_24h, trade_count_24h = row

    first_trade = (
        await db.execute(
            select(Trade)
            .where(Trade.market_id == market_id, Trade.occurred_at >= since)
            .order_by(Trade.sequence.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    last_trade = (
        await db.execute(
            select(Trade).where(Trade.market_id == market_id).order_by(Trade.sequence.desc()).limit(1)
        )
    ).scalar_one_or_none()

    open_24h = Decimal(first_trade.price) if first_trade else None
    last_price = Decimal(last_trade.price) if last_trade else None

    change_pct = None
    if open_24h is not None and last_price is not None and open_24h != 0:
        change_pct = ((last_price - open_24h) / open_24h) * Decimal(100)

    return TickerSnapshot(
        market_id=str(market_id),
        last_price=last_price,
        open_24h=open_24h,
        high_24h=Decimal(high_24h) if high_24h is not None else None,
        low_24h=Decimal(low_24h) if low_24h is not None else None,
        volume_24h=Decimal(volume_24h) if volume_24h is not None else Decimal(0),
        quote_volume_24h=Decimal(quote_volume_24h) if quote_volume_24h is not None else Decimal(0),
        trade_count_24h=trade_count_24h or 0,
        change_24h_pct=change_pct,
    )


async def get_ticker_cached(db: AsyncSession, redis_client: redis.Redis, market_id: str) -> TickerSnapshot:
    cached = await redis_client.get(_cache_key(market_id))
    if cached is not None:
        return TickerSnapshot.from_cache_dict(json.loads(cached))

    snapshot = await compute_ticker(db, market_id)
    await redis_client.set(
        _cache_key(market_id), json.dumps(snapshot.to_cache_dict()), ex=settings.TICKER_CACHE_TTL_SECONDS
    )
    return snapshot
