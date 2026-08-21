"""Auth dependencies.

Unlike api-gateway, this service has no `users` table of its own -- it is
an internal service that trusts the signature on an access token minted by
api-gateway and reads the `sub` (user id) and `role` claims directly out of
it. This keeps market-data-service from needing a second copy of user
state that could drift from the source of truth in api-gateway's database.

Most market-data endpoints (ticker, candles, trades, order book) are
public/unauthenticated -- market data isn't user-specific. Auth here
matters for the admin-only asset/market configuration endpoints, and
get_caller()/require_admin_or_service() exist for consistency with
ledger-service and wallet-service's pattern, in case a future service
(e.g. the matching engine) needs to provision markets programmatically.
"""

import hmac
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.security import InvalidTokenError, decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CallerIdentity:
    user_id: str
    role: str  # "user" | "admin" | "service"


async def get_current_caller(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CallerIdentity:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    user_id = payload.get("sub")
    role = payload.get("role", "user")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    return CallerIdentity(user_id=user_id, role=role)


def _service_key_is_valid(provided: str | None) -> bool:
    if not provided or not settings.INTERNAL_SERVICE_KEY:
        return False
    return hmac.compare_digest(provided, settings.INTERNAL_SERVICE_KEY)


async def get_caller(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CallerIdentity:
    """Accepts either an internal-service key or a user/admin bearer token.

    Used by endpoints that a backend service must be able to call on a
    user's behalf (e.g. wallet-service posting a deposit's ledger
    transaction) but that should also remain directly usable by an admin.
    """
    service_key = request.headers.get("X-Internal-Service-Key")
    if _service_key_is_valid(service_key):
        caller_service = request.headers.get("X-Internal-Service-Name", "unknown-service")
        return CallerIdentity(user_id=f"service:{caller_service}", role="service")

    return await get_current_caller(credentials)


async def require_admin(caller: CallerIdentity = Depends(get_current_caller)) -> CallerIdentity:
    if caller.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return caller


async def require_admin_or_service(caller: CallerIdentity = Depends(get_caller)) -> CallerIdentity:
    if caller.role not in ("admin", "service"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return caller
