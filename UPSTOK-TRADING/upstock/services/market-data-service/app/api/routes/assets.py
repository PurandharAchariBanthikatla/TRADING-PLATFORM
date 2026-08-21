from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin_or_service
from app.db.session import get_db
from app.models.asset import Asset
from app.schemas.marketdata import AssetCreateRequest, AssetResponse

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetResponse])
async def list_assets(db: AsyncSession = Depends(get_db)):
    """Public/unauthenticated -- asset configuration isn't sensitive and
    the trading UI (phase 5) needs it to render symbol pickers etc.
    """
    result = await db.execute(select(Asset).order_by(Asset.symbol))
    return list(result.scalars().all())


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    payload: AssetCreateRequest,
    _admin=Depends(require_admin_or_service),
    db: AsyncSession = Depends(get_db),
):
    asset = Asset(symbol=payload.symbol, name=payload.name, decimals=payload.decimals)
    db.add(asset)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Asset {payload.symbol} already exists"
        ) from exc

    await db.refresh(asset)
    return asset
