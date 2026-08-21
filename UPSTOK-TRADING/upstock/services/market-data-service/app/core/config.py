from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = Field(default="development")
    SERVICE_NAME: str = Field(default="market-data-service")
    LOG_LEVEL: str = Field(default="INFO")

    DATABASE_URL: str = Field(default="postgresql+asyncpg://exchange:exchange@postgres:5432/exchange")
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=30)

    JWT_SECRET_KEY: str = Field(default="CHANGE_ME_IN_PRODUCTION")
    JWT_ALGORITHM: str = Field(default="HS256")
    INTERNAL_SERVICE_KEY: str = Field(default="CHANGE_ME_IN_PRODUCTION")

    API_V1_PREFIX: str = Field(default="/api/v1")

    # --- Event bus (Redis Streams; see app/core/event_bus.py docstring for
    # why Redis Streams stands in for Kafka/Redpanda in this environment) ---
    REDIS_URL: str = Field(default="redis://redis:6379/1")
    EVENT_STREAM_MAX_DELIVERY_ATTEMPTS: int = Field(default=5)
    EVENT_STREAM_CLAIM_MIN_IDLE_MS: int = Field(default=30_000)
    EVENT_STREAM_MAXLEN_APPROX: int = Field(default=100_000)

    # --- Paper market-data simulator (phase 3 stand-in for real
    # matching-engine-produced trades; see app/core/simulator.py) ---
    SIMULATOR_ENABLED: bool = Field(default=True)
    SIMULATOR_TICK_INTERVAL_SECONDS: float = Field(default=1.0)
    SIMULATOR_SEED: int = Field(default=1337)

    TICKER_CACHE_TTL_SECONDS: int = Field(default=5)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
