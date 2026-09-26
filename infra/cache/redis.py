"""Redis: FSM-кэш aiogram, rate-limit, кэш ответов LLM.

Потеря Redis не теряет прогресс опроса — источник истины в Postgres.
"""

from __future__ import annotations

from redis.asyncio import Redis

from core.config import RedisSettings


def build_redis(settings: RedisSettings) -> Redis:
    return Redis.from_url(settings.dsn, decode_responses=True)
