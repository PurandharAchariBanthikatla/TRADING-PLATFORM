"""Access-token verification.

This service trusts access tokens minted by api-gateway (see
services/api-gateway/app/core/security.py for issuance). It only ever
*verifies* signatures here -- there is no login/refresh flow in this
service, which is why there's no create_access_token counterpart.
"""

from enum import Enum

from jose import JWTError, jwt

from app.core.config import settings


class TokenType(str, Enum):
    ACCESS = "access"


class InvalidTokenError(Exception):
    pass


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise InvalidTokenError(f"expected token type 'access', got '{payload.get('type')}'")

    return payload
