"""Password hashing and JWT token issuance/verification.

Design notes:
- Access tokens are short-lived (default 15 min) and carry no server-side
  state -- they're verified by signature alone, which keeps the hot path
  (every authenticated request) free of a DB/Redis round trip.
- Refresh tokens are long-lived, opaque-to-the-client JWTs whose jti is
  persisted in Postgres (see models.refresh_token) so they can be revoked
  individually (logout, "log out other devices") or in bulk (password
  change, suspected compromise). Redis is used as a fast-path revocation
  cache so we don't hit Postgres on every refresh.
"""
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.BCRYPT_ROUNDS)


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(Exception):
    pass


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict | None = None,
) -> tuple[str, str, datetime]:
    now = datetime.now(UTC)
    expire = now + expires_delta
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": expire,
        "jti": jti,
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expire


def create_access_token(user_id: str, extra_claims: dict | None = None) -> tuple[str, str, datetime]:
    return _create_token(
        subject=user_id,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims=extra_claims,
    )


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    return _create_token(
        subject=user_id,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != expected_type.value:
        raise InvalidTokenError(f"expected token type '{expected_type.value}', got '{payload.get('type')}'")

    return payload
