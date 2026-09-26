"""Мягкий rate-limit на Redis. Недоступность Redis не блокирует пользователя."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from redis.asyncio import Redis

from infra.telemetry import get_logger

log = get_logger("bot.throttle")


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, limit: int = 20, window_seconds: int = 60) -> None:
        self._redis = redis
        self._limit = limit
        self._window = window_seconds

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_id = None
        if isinstance(event, Update) and hasattr(event.event, "from_user"):
            user = event.event.from_user
            tg_id = getattr(user, "id", None)

        if tg_id is not None:
            try:
                key = f"throttle:{tg_id}"
                count = await self._redis.incr(key)
                if count == 1:
                    await self._redis.expire(key, self._window)
                if count > self._limit:
                    log.warning("bot.throttled", tg_id=tg_id, count=count)
                    return None
            except Exception as exc:  # noqa: BLE001
                log.warning("bot.throttle_unavailable", error=str(exc))

        return await handler(event, data)
