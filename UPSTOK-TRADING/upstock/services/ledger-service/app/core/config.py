"""Centralized application configuration.

Mirrors services/api-gateway/app/core/config.py by convention. The ledger
service does NOT issue tokens -- it only verifies access tokens minted by
api-gateway, so it needs the same JWT_SECRET_KEY/JWT_ALGORITHM to validate
signatures. In a real deployment this secret is injected identically into
both services from the same secret-manager entry, never duplicated by hand.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    ENVIRONMENT: str = Field(default="development")  # development | staging | production
    SERVICE_NAME: str = Field(default="ledger-service")
    LOG_LEVEL: str = Field(default="INFO")

    # --- Database ---
    DATABASE_URL: str = Field(default="postgresql+asyncpg://exchange:exchange@postgres:5432/exchange")
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30)

    # --- JWT verification (tokens are minted by api-gateway; this service
    # only verifies signatures, it never issues tokens itself) ---
    JWT_SECRET_KEY: str = Field(default="CHANGE_ME_IN_PRODUCTION")
    JWT_ALGORITHM: str = Field(default="HS256")

    # --- Service-to-service auth (see app/api/deps.py get_caller()) ---
    INTERNAL_SERVICE_KEY: str = Field(default="CHANGE_ME_IN_PRODUCTION")

    # --- Misc ---
    API_V1_PREFIX: str = Field(default="/api/v1")

    # Largest number of entries a single ledger transaction may contain.
    # Bounds lock-ordering / lock-count on the hot posting path.
    MAX_ENTRIES_PER_TRANSACTION: int = Field(default=32)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
