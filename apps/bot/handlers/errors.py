"""Глобальный обработчик ошибок: пользователь не должен остаться без ответа."""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, ErrorEvent, Message

from apps.bot import texts
from core.config import get_settings
from infra.telemetry import get_logger

log = get_logger("bot.errors")

router = Router(name="errors")


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    log.error(
        "bot.unhandled",
        error=str(event.exception),
        error_type=type(event.exception).__name__,
        update_id=event.update.update_id,
    )

    support = get_settings().content.support_contact
    target = event.update.message or event.update.callback_query
    try:
        if isinstance(target, CallbackQuery):
            await target.answer()
            if isinstance(target.message, Message):
                await target.message.answer(texts.ERROR.format(support=support))
        elif isinstance(target, Message):
            await target.answer(texts.ERROR.format(support=support))
    except Exception as exc:  # noqa: BLE001 — уведомить не вышло, но апдейт гасим
        log.error("bot.error_reply_failed", error=str(exc))

    return True
