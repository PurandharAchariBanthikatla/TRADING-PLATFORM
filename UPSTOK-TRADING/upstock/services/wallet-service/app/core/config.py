from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = Field(default="development")
    SERVICE_NAME: str = Field(default="wallet-service")
    LOG_LEVEL: str = Field(default="INFO")

    DATABASE_URL: str = Field(default="postgresql+asyncpg://exchange:exchange@postgres:5432/exchange")
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30)

    # JWT verification -- identical requirement to ledger-service: this
    # service never issues tokens, only verifies ones api-gateway minted.
    JWT_SECRET_KEY: str = Field(default="CHANGE_ME_IN_PRODUCTION")
    JWT_ALGORITHM: str = Field(default="HS256")

    # Calls into ledger-service as a trusted internal service (see
    # app/clients/ledger_client.py and ledger-service's app/api/deps.py).
    LEDGER_SERVICE_BASE_URL: str = Field(default="http://ledger-service:8000/api/v1")
    INTERNAL_SERVICE_KEY: str = Field(default="CHANGE_ME_IN_PRODUCTION")
    LEDGER_CLIENT_TIMEOUT_SECONDS: float = Field(default=10.0)

    API_V1_PREFIX: str = Field(default="/api/v1")

    # Paper-funds withdrawal limits. Deliberately flat (not asset-aware,
    # not tiered by KYC level) at this stage -- per-asset precision and
    # limits arrive with Phase 3 market/asset configuration, and
    # KYC-tiered limits are Phase 7 (admin) territory. This is enough to
    # exercise and test the approval workflow honestly today.
    MAX_WITHDRAWAL_PER_TRANSACTION: Decimal = Field(default=Decimal("10000"))
    MAX_WITHDRAWAL_PER_DAY: Decimal = Field(default=Decimal("25000"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
