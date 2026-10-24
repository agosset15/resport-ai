"""Отправка картинок с переиспользованием file_id.

Картинки зон боли одни и те же для всех пользователей. Загружать файл в Telegram на
каждую сессию незачем: после первой отправки запоминаем `file_id` и дальше отправляем
его. Кэш процессный и намеренно простой — потеря при рестарте стоит одну загрузку.

Лежит в `apps/bot`, потому что это транспортная забота: `core` про Telegram не знает.
"""

from __future__ import annotations

from pathlib import Path

from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from infra.telemetry import get_logger

log = get_logger("bot.media")

#: image_id -> file_id в Telegram.
_FILE_IDS: dict[str, str] = {}

ALLOWED_SUFFIXES = (".jpg", ".jpeg", ".png")

#: Telegram обрезает подпись к фото на 1024 символах.
CAPTION_LIMIT = 1024


def find_image(directory: Path, image_id: str) -> Path | None:
    """Путь к картинке или None, если заказчик её ещё не прислал."""
    for suffix in ALLOWED_SUFFIXES:
        candidate = directory / f"{image_id}{suffix}"
        if candidate.is_file():
            return candidate
    return None


async def send_image(
    message: Message,
    directory: Path,
    image_id: str,
    *,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Отправляет картинку. False — файла нет, вызывающий продолжает без него."""
    cached = _FILE_IDS.get(image_id)
    photo: str | FSInputFile

    if cached is not None:
        photo = cached
    else:
        path = find_image(directory, image_id)
        if path is None:
            log.info("media.image_missing", image_id=image_id, directory=str(directory))
            return False
        photo = FSInputFile(path)

    sent = await message.answer_photo(
        photo=photo,
        caption=caption[:CAPTION_LIMIT],
        reply_markup=reply_markup,
    )
    if cached is None and sent.photo:
        _FILE_IDS[image_id] = sent.photo[-1].file_id
    return True
