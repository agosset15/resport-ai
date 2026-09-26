"""Фоновые задачи: ежедневные напоминания о чек-ине.

Раз в минуту смотрим активные планы и сравниваем локальное время пользователя с его
reminder_time. Повторную отправку в тот же день блокирует ключ в Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from dishka import AsyncContainer, Scope
from redis.asyncio import Redis

from apps.bot import texts
from apps.bot.keyboards.common import checkin_start_kb
from core.domain.enums import EventType
from core.services.protocols import EventRepository, PlanRepository
from infra.telemetry import get_logger

log = get_logger("worker.reminders")

SENT_TTL_SECONDS = 26 * 3600


def _local_now(timezone: str) -> datetime:
    try:
        return datetime.now(ZoneInfo(timezone))
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.now(UTC)


async def send_due_reminders(container: AsyncContainer, bot: Bot, redis: Redis | None) -> None:
    async with container(scope=Scope.REQUEST) as request_container:
        plans: PlanRepository = await request_container.get(PlanRepository)
        events: EventRepository = await request_container.get(EventRepository)
        active = await plans.list_active()

        for plan, user in active:
            if user.reminder_time is None:
                continue
            now = _local_now(user.timezone)
            if (now.hour, now.minute) != (user.reminder_time.hour, user.reminder_time.minute):
                continue

            key = f"reminder:{user.id}:{now.date().isoformat()}"
            if redis is not None:
                try:
                    if not await redis.set(key, "1", ex=SENT_TTL_SECONDS, nx=True):
                        continue
                except Exception as exc:  # noqa: BLE001 — Redis недоступен: шлём как есть
                    log.warning("worker.redis_unavailable", error=str(exc))

            try:
                await bot.send_message(
                    user.tg_id, texts.REMINDER_PING, reply_markup=checkin_start_kb()
                )
            except TelegramForbiddenError:
                log.info("worker.blocked_by_user", tg_id=user.tg_id)
                continue
            except TelegramRetryAfter as exc:
                log.warning("worker.rate_limited", retry_after=exc.retry_after)
                continue
            except Exception as exc:  # noqa: BLE001 — один пользователь не ломает рассылку
                log.error("worker.send_failed", tg_id=user.tg_id, error=str(exc))
                continue

            await events.add(
                EventType.REMINDER_SENT,
                user_id=user.id,
                session_id=plan.session_id,
                payload={"plan_id": str(plan.id)},
            )
            log.info("worker.reminder_sent", tg_id=user.tg_id, plan_id=str(plan.id))
