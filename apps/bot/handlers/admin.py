"""Админ-выгрузка CSV. Панели в MVP нет — аналитика в Metabase поверх той же Postgres."""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from core.config import BotSettings
from core.services.export import ExportService

router = Router(name="admin")


def _is_admin(message: Message, settings: BotSettings) -> bool:
    return message.from_user is not None and message.from_user.id in settings.admin_tg_ids


async def _send_csv(message: Message, content: str, name: str) -> None:
    if not content.strip():
        await message.answer(texts.EXPORT_EMPTY)
        return
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M")
    await message.answer_document(
        BufferedInputFile(content.encode("utf-8-sig"), filename=f"{name}_{stamp}.csv")
    )


@router.message(Command("export_sessions"))
@inject
async def export_sessions(
    message: Message,
    settings: FromDishka[BotSettings],
    export: FromDishka[ExportService],
) -> None:
    if not _is_admin(message, settings):
        await message.answer(texts.ADMIN_ONLY)
        return
    await _send_csv(message, await export.sessions_csv(), "sessions")


@router.message(Command("export_checkins"))
@inject
async def export_checkins(
    message: Message,
    settings: FromDishka[BotSettings],
    export: FromDishka[ExportService],
) -> None:
    if not _is_admin(message, settings):
        await message.answer(texts.ADMIN_ONLY)
        return
    await _send_csv(message, await export.checkins_csv(), "checkins")


@router.message(Command("stats"))
@inject
async def stats(
    message: Message,
    settings: FromDishka[BotSettings],
    export: FromDishka[ExportService],
) -> None:
    if not _is_admin(message, settings):
        await message.answer(texts.ADMIN_ONLY)
        return
    rows = await export.funnel()
    if not rows:
        await message.answer(texts.EXPORT_EMPTY)
        return
    body = "\n".join(f"{row['status']}: {row['count']}" for row in rows)
    await message.answer(f"<b>Сессии по статусам</b>\n{body}")
