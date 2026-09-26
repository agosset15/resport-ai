"""Long polling для локальной разработки: python -m apps.bot."""

from __future__ import annotations

import asyncio

from apps.bot.factory import build_runtime, set_commands
from apps.di import build_container
from core.config import get_settings
from core.domain.scenario import ScenarioRegistry
from infra.telemetry import get_logger, setup_logging

log = get_logger("bot.polling")


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.app.log_level, settings.app.log_json)

    if not settings.bot.token.get_secret_value():
        raise SystemExit("BOT_TOKEN не задан")

    container = build_container()
    registry = await container.get(ScenarioRegistry)
    log.info("scenarios.loaded", ids=list(registry.ids()))

    bot, dispatcher = await build_runtime(container, settings.bot, settings.redis)
    await set_commands(bot)
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await container.close()


if __name__ == "__main__":
    asyncio.run(run())
