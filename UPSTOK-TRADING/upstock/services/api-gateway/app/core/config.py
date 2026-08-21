"""Centralized application configuration.

All values are sourced from environment variables so the same image can be
promoted from local -> staging -> production without rebuilding. See
.env.example for the full list of variables this service understands.
"""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    ENVIRONMENT: str = Field(default="development")  # development | staging | production
    SERVICE_NAME: str = Field(default="api-gateway")
    LOG_LEVEL: str = Field(default="INFO")

    # --- Database ---
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://exchange:exchange@postgres:5432/exchange"
    )
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30)

    # --- Redis (sessions / rate limiting / refresh-token blacklist) ---
    REDIS_URL: str = Field(default="redis://redis:6379/0")

    # --- JWT / auth ---
    JWT_SECRET_KEY: str = Field(default="CHANGE_ME_IN_PRODUCTION")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)

    # --- Password hashing ---
    BCRYPT_ROUNDS: int = Field(default=12)

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN_ATTEMPTS: int = Field(default=5)
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = Field(default=300)
    RATE_LIMIT_REGISTER_ATTEMPTS: int = Field(default=3)
    RATE_LIMIT_REGISTER_WINDOW_SECONDS: int = Field(default=3600)

    # --- CORS ---
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def split_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # --- Misc ---
    API_V1_PREFIX: str = Field(default="/api/v1")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
