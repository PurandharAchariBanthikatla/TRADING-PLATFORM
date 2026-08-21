from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_or_service
from app.db.session import get_db
from app.models.market import Market
from app.schemas.marketdata import MarketCreateRequest, MarketResponse, MarketStatusUpdateRequest

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=list[MarketResponse])
async def list_markets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Market).order_by(Market.symbol))
    return list(result.scalars().all())


@router.get("/{symbol}", response_model=MarketResponse)
async def get_market(symbol: str, db: AsyncSession = Depends(get_db)):
    market = (await db.execute(select(Market).where(Market.symbol == symbol.upper()))).scalar_one_or_none()
    if market is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Market not found")
    return market


@router.post("", response_model=MarketResponse, status_code=status.HTTP_201_CREATED)
async def create_market(
    payload: MarketCreateRequest,
    _admin=Depends(require_admin_or_service),
    db: AsyncSession = Depends(get_db),
):
    if payload.max_quantity <= payload.min_quantity:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="max_quantity must exceed min_quantity"
        )

    symbol = f"{payload.base_asset}-{payload.quote_asset}"
    market = Market(
        symbol=symbol,
        base_asset=payload.base_asset,
        quote_asset=payload.quote_asset,
        price_precision=payload.price_precision,
        quantity_precision=payload.quantity_precision,
        tick_size=payload.tick_size,
        lot_size=payload.lot_size,
        min_quantity=payload.min_quantity,
        max_quantity=payload.max_quantity,
        min_notional=payload.min_notional,
        maker_fee_bps=payload.maker_fee_bps,
        taker_fee_bps=payload.taker_fee_bps,
    )
    db.add(market)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Market {symbol} already exists") from exc

    await db.refresh(market)
    return market


@router.patch("/{symbol}/status", response_model=MarketResponse)
async def update_market_status(
    symbol: str,
    payload: MarketStatusUpdateRequest,
    _admin=Depends(require_admin_or_service),
    db: AsyncSession = Depends(get_db),
):
    market = (await db.execute(select(Market).where(Market.symbol == symbol.upper()))).scalar_one_or_none()
    if market is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Market not found")

    market.status = payload.status
    await db.commit()
    await db.refresh(market)
    return market
