from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.logging import get_logger
from app.core.rate_limit import RateLimitExceeded, enforce_rate_limit
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserPublic,
)

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _issue_token_pair(db: AsyncSession, user: User, request: Request) -> TokenResponse:
    access_token, _access_jti, _access_exp = create_access_token(
        str(user.id), extra_claims={"role": user.role.value}
    )
    refresh_token, refresh_jti, refresh_exp = create_refresh_token(str(user.id))

    db.add(
        RefreshToken(
            user_id=user.id,
            jti=refresh_jti,
            expires_at=refresh_exp,
            user_agent=request.headers.get("user-agent"),
            ip_address=_client_ip(request),
        )
    )
    await db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await enforce_rate_limit(
            key=f"ratelimit:register:{_client_ip(request)}",
            max_attempts=settings.RATE_LIMIT_REGISTER_ATTEMPTS,
            window_seconds=settings.RATE_LIMIT_REGISTER_WINDOW_SECONDS,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts, please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # Deliberately generic: don't confirm/deny which emails are registered.
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Unable to register with the provided details."
        ) from exc

    await db.refresh(user)
    log.info("user_registered", user_id=str(user.id))
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    ip = _client_ip(request)
    try:
        await enforce_rate_limit(
            key=f"ratelimit:login:{ip}:{payload.email.lower()}",
            max_attempts=settings.RATE_LIMIT_LOGIN_ATTEMPTS,
            window_seconds=settings.RATE_LIMIT_LOGIN_WINDOW_SECONDS,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts, please try again later.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = result.scalar_one_or_none()

    # Constant-shape response whether the email exists or not, to avoid
    # leaking account existence via timing/response differences.
    if user is None or not verify_password(payload.password, user.hashed_password):
        log.warning("login_failed", email=payload.email.lower(), ip=ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password.")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account is disabled.")

    log.info("user_logged_in", user_id=str(user.id))
    return await _issue_token_pair(db, user, request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token_payload = decode_token(payload.refresh_token, expected_type=TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token.") from exc

    jti = token_payload["jti"]
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    stored = result.scalar_one_or_none()

    if stored is None or stored.revoked or stored.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Refresh token is no longer valid.")

    user_result = await db.execute(select(User).where(User.id == stored.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")

    # Rotate: revoke the presented refresh token and issue a brand new pair.
    # This bounds the damage from a leaked refresh token to a single use.
    stored.revoked = True
    await db.commit()

    return await _issue_token_pair(db, user, request)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        token_payload = decode_token(payload.refresh_token, expected_type=TokenType.REFRESH)
    except InvalidTokenError:
        # Logging out with an already-invalid token is a no-op success.
        return

    jti = token_payload["jti"]
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    stored = result.scalar_one_or_none()
    if stored is not None:
        stored.revoked = True
        await db.commit()
    # See app.api.deps.get_current_user for why we don't also try to
    # denylist the access token here.


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(get_current_user)):
    return user
