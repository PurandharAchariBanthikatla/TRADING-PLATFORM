"""Fixed-window rate limiting backed by Redis.

Used to throttle brute-force login attempts and registration abuse. Keyed by
a caller-supplied identifier (typically client IP + route) so different
routes get independent budgets.
"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit exceeded, retry after {retry_after_seconds}s")


async def enforce_rate_limit(key: str, max_attempts: int, window_seconds: int) -> None:
    """Raises RateLimitExceeded if `key` has been hit more than `max_attempts`
    times within `window_seconds`. Uses a simple INCR + EXPIRE fixed window,
    which is O(1) and good enough for auth endpoints; a sliding-window log
    would be used for the public trading-API rate limits.
    """
    redis = get_redis()
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)
    if current > max_attempts:
        ttl = await redis.ttl(key)
        raise RateLimitExceeded(retry_after_seconds=max(ttl, 1))
