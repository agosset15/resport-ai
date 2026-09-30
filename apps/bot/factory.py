"""Сборка aiogram-приложения. Транспорт: логики здесь нет."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from dishka import AsyncContainer
from dishka.integrations.aiogram import setup_dishka
from redis.asyncio import Redis

from apps.bot.handlers import admin, errors, onboarding, tracker, triage
from apps.bot.middlewares.context import LoggingContextMiddleware
from apps.bot.middlewares.throttle import ThrottleMiddleware
from core.config import BotSettings, RedisSettings
from infra.cache.redis import build_redis
from infra.telemetry import get_logger

log = get_logger("bot.factory")

COMMANDS = [
    ("start", "Начать заново"),
    ("plan", "Текущий этап плана"),
    ("checkin", "Отметить день"),
    ("reminder", "Время напоминания"),
    ("help", "Справка"),
]


def build_bot(settings: BotSettings) -> Bot:
    session = None
    if settings.api_server_url:
        api = TelegramAPIServer.from_base(
            settings.api_server_url, is_local=settings.api_server_local
        )
        session = AiohttpSession(api=api)
        log.info(
            "bot.custom_api_server",
            url=settings.api_server_url,
            local=settings.api_server_local,
        )
    return Bot(
        token=settings.token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


def build_dispatcher(container: AsyncContainer, redis: Redis | None = None) -> Dispatcher:
    storage = RedisStorage(redis) if redis is not None else MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.update.outer_middleware(LoggingContextMiddleware())
    if redis is not None:
        dp.update.outer_middleware(ThrottleMiddleware(redis))

    dp.include_router(onboarding.router)
    dp.include_router(triage.router)
    dp.include_router(tracker.router)
    dp.include_router(admin.router)
    dp.include_router(errors.router)

    setup_dishka(container=container, router=dp, auto_inject=False)
    return dp


async def set_commands(bot: Bot) -> None:
    from aiogram.types import BotCommand

    await bot.set_my_commands(
        [BotCommand(command=name, description=desc) for name, desc in COMMANDS]
    )


async def build_runtime(
    container: AsyncContainer, bot_settings: BotSettings, redis_settings: RedisSettings
) -> tuple[Bot, Dispatcher]:
    bot = build_bot(bot_settings)
    redis = build_redis(redis_settings)
    try:
        await redis.ping()
    except Exception as exc:  # noqa: BLE001
        log.warning("bot.redis_unavailable", error=str(exc))
        await redis.aclose()
        redis = None  # type: ignore[assignment]
    dispatcher = build_dispatcher(container, redis)
    return bot, dispatcher
