"""Кэш ответов LLM в Redis. Недоступность Redis не должна ломать поток — см. LlmRunner."""

from __future__ import annotations

from redis.asyncio import Redis

PREFIX = "llm:v1:"


class RedisLlmCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> str | None:
        value = await self._redis.get(PREFIX + key)
        return value.decode() if isinstance(value, bytes) else value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self._redis.set(PREFIX + key, value, ex=ttl_seconds)
