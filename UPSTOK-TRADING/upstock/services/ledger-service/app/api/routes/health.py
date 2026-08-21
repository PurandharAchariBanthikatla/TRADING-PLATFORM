from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness():
    """Process is up. Used by Docker HEALTHCHECK / orchestrator liveness probe."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(response: Response, db: AsyncSession = Depends(get_db)):
    """Process is up AND Postgres is reachable. Used to gate traffic during
    rolling deploys.
    """
    checks = {"database": "ok"}
    healthy = True

    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        checks["database"] = "unreachable"
        healthy = False

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ok" if healthy else "degraded", "checks": checks}
