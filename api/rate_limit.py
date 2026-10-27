"""Redis-backed fixed-window quotas with a development-safe local fallback."""

from __future__ import annotations

import asyncio
import time

from fastapi import HTTPException, status

from .config import settings
from .errors import api_error


class RateLimiter:
    def __init__(self):
        self._redis = None
        self._local: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        try:
            from redis.asyncio import from_url

            client = from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
            await client.ping()
            self._redis = client
        except Exception:
            self._redis = None
            if settings.redis_required:
                raise RuntimeError("Redis is required but unavailable")

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    @staticmethod
    def _key(user_id: str, bucket: str, window: int) -> str:
        return f"argus:rate:{bucket}:{user_id}:{int(time.time()) // window}"

    async def _increment(self, key: str, window: int) -> int:
        if self._redis is not None:
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, window + 1)
            return int(count)
        async with self._lock:
            count, expires = self._local.get(key, (0, time.monotonic() + window))
            if expires <= time.monotonic():
                count, expires = 0, time.monotonic() + window
            count += 1
            self._local[key] = (count, expires)
            if len(self._local) > 2000:
                now = time.monotonic()
                self._local = {k: v for k, v in self._local.items() if v[1] > now}
            return count

    async def count(self, user_id: str, bucket: str, window: int) -> int:
        """Current count in this window, without adding to it."""
        key = self._key(user_id, bucket, window)
        if self._redis is not None:
            return int(await self._redis.get(key) or 0)
        async with self._lock:
            count, expires = self._local.get(key, (0, 0.0))
            return count if expires > time.monotonic() else 0

    async def record(self, user_id: str, bucket: str, window: int) -> None:
        """Count an event without enforcing a limit (checked later with count())."""
        await self._increment(self._key(user_id, bucket, window), window)

    async def consume(self, user_id: str, bucket: str, limit: int, window: int) -> None:
        count = await self._increment(self._key(user_id, bucket, window), window)
        if count > limit:
            raise api_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "rate_limited",
                "Request limit reached. Please try again shortly.",
                headers={"Retry-After": str(window)},
            )


limiter = RateLimiter()
