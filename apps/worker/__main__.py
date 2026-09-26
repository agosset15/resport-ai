"""Планировщик: python -m apps.worker."""

from __future__ import annotations

import asyncio
import contextlib

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from apps.bot.factory import build_bot
from apps.di import build_container
from apps.worker.jobs import send_due_reminders
from core.config import get_settings
from core.domain.scenario import ScenarioRegistry
from infra.cache.redis import build_redis
from infra.telemetry import get_logger, setup_logging

log = get_logger("worker")


async def run() -> None:
    settings = get_settings()
    setup_logging(settings.app.log_level, settings.app.log_json)

    if not settings.bot.token.get_secret_value():
        raise SystemExit("BOT_TOKEN не задан")

    container = build_container()
    registry = await container.get(ScenarioRegistry)
    log.info("scenarios.loaded", ids=list(registry.ids()))

    bot = build_bot(settings.bot)
    redis = build_redis(settings.redis)
    try:
        await redis.ping()
    except Exception as exc:  # noqa: BLE001
        log.warning("worker.redis_unavailable", error=str(exc))
        await redis.aclose()
        redis = None  # type: ignore[assignment]

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        send_due_reminders,
        CronTrigger(second=0),
        args=(container, bot, redis),
        id="reminders",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("worker.started")

    stop = asyncio.Event()
    try:
        await stop.wait()
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        if redis is not None:
            await redis.aclose()
        await container.close()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())
