from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ticker import get_ticker_cached
from app.db.session import get_db
from app.models.candle import Candle, CandleInterval
from app.models.market import Market
from app.models.orderbook import OrderBookSnapshot
from app.models.trade import Trade
from app.schemas.marketdata import CandleResponse, OrderBookResponse, TickerResponse, TradeResponse

router = APIRouter(prefix="/marketdata", tags=["marketdata"])


async def _get_market_or_404(db: AsyncSession, symbol: str) -> Market:
    market = (await db.execute(select(Market).where(Market.symbol == symbol.upper()))).scalar_one_or_none()
    if market is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Market not found")
    return market


@router.get("/{symbol}/ticker", response_model=TickerResponse)
async def get_ticker(symbol: str, request: Request, db: AsyncSession = Depends(get_db)):
    market = await _get_market_or_404(db, symbol)
    snapshot = await get_ticker_cached(db, request.app.state.redis_client, str(market.id))
    return TickerResponse(
        market_id=snapshot.market_id,
        symbol=market.symbol,
        last_price=snapshot.last_price,
        open_24h=snapshot.open_24h,
        high_24h=snapshot.high_24h,
        low_24h=snapshot.low_24h,
        volume_24h=snapshot.volume_24h,
        quote_volume_24h=snapshot.quote_volume_24h,
        trade_count_24h=snapshot.trade_count_24h,
        change_24h_pct=snapshot.change_24h_pct,
    )


@router.get("/{symbol}/candles", response_model=list[CandleResponse])
async def get_candles(
    symbol: str,
    interval: CandleInterval = Query(default=CandleInterval.ONE_MINUTE),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    market = await _get_market_or_404(db, symbol)
    result = await db.execute(
        select(Candle)
        .where(Candle.market_id == market.id, Candle.interval == interval)
        .order_by(Candle.open_time.desc())
        .limit(limit)
    )
    candles = list(result.scalars().all())
    return [CandleResponse.model_validate(c) for c in reversed(candles)]


@router.get("/{symbol}/trades", response_model=list[TradeResponse])
async def get_recent_trades(
    symbol: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    market = await _get_market_or_404(db, symbol)
    result = await db.execute(
        select(Trade).where(Trade.market_id == market.id).order_by(Trade.sequence.desc()).limit(limit)
    )
    return list(reversed(result.scalars().all()))


@router.get("/{symbol}/orderbook", response_model=OrderBookResponse)
async def get_orderbook(
    symbol: str,
    depth: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    market = await _get_market_or_404(db, symbol)
    snapshot = (
        await db.execute(
            select(OrderBookSnapshot)
            .where(OrderBookSnapshot.market_id == market.id)
            .order_by(OrderBookSnapshot.sequence.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No order book data yet for this market")

    return OrderBookResponse(
        sequence=snapshot.sequence,
        bids=snapshot.bids[:depth],
        asks=snapshot.asks[:depth],
        snapshot_time=snapshot.snapshot_time,
    )
