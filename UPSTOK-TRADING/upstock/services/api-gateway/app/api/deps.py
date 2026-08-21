import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, TokenType, decode_token
from app.db.session import get_db
from app.models.user import User, UserRole

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from a bearer access token.

    Revocation model: access tokens are stateless and self-expire within
    ACCESS_TOKEN_EXPIRE_MINUTES (default 15). We deliberately do NOT try to
    denylist individual access-token jtis on logout -- the client only holds
    the refresh token by the time /logout is called, so there's nothing
    correct to denylist against. Instead:
      - logout revokes the refresh token, so no new access tokens can be
        minted for that session; the last access token simply expires soon.
      - admin-disable takes effect on the *next* request regardless of a
        still-valid access token, because is_active is checked against
        Postgres below on every call.
    A true instant-kill-switch (e.g. for a compromised account) would add a
    per-user "tokens_valid_after" timestamp checked here against the token's
    `iat` claim; that lands alongside the security-settings/session-management
    screens rather than in this first auth slice.
    """
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc

    user_id = payload.get("sub")
    try:
        user_uuid = uuid.UUID(user_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return user


def require_role(*allowed_roles: UserRole):
    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _checker


require_admin = require_role(UserRole.ADMIN)
