"""Привязка контекста логов к апдейту: tg_id и update_id видны в каждой строке."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from infra.telemetry import bind_request_context, clear_request_context, get_logger

log = get_logger("bot")


class LoggingContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        clear_request_context()
        if isinstance(event, Update):
            user = event.event.from_user if hasattr(event.event, "from_user") else None
            bind_request_context(
                update_id=event.update_id,
                tg_id=getattr(user, "id", None),
            )
        try:
            return await handler(event, data)
        except Exception:
            log.exception("bot.handler_failed")
            raise
        finally:
            clear_request_context()
