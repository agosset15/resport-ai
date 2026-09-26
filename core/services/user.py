"""Пользователь: регистрация, согласие, время напоминаний."""

from __future__ import annotations

from datetime import UTC, datetime, time

from core.config import ContentSettings
from core.domain.entities import User
from core.domain.enums import EventType
from core.services.protocols import EventRepository, UserRepository


class UserService:
    def __init__(
        self,
        users: UserRepository,
        events: EventRepository,
        content: ContentSettings,
    ) -> None:
        self._users = users
        self._events = events
        self._content = content

    @property
    def consent_version(self) -> str:
        return self._content.consent_version

    async def get_or_create(self, tg_id: int, username: str | None, locale: str = "ru") -> User:
        user = await self._users.get_by_tg_id(tg_id)
        if user is not None:
            return user
        user = await self._users.create(tg_id=tg_id, username=username, locale=locale)
        await self._events.add(EventType.BOT_STARTED, user_id=user.id, payload={"tg_id": tg_id})
        return user

    def needs_consent(self, user: User) -> bool:
        return not user.has_consent(self._content.consent_version)

    async def accept_consent(self, user: User) -> User:
        now = datetime.now(UTC)
        version = self._content.consent_version
        await self._users.set_consent(user.id, version, now)
        await self._events.add(
            EventType.CONSENT_GIVEN, user_id=user.id, payload={"version": version}
        )
        user.consent_version = version
        user.consent_at = now
        return user

    async def set_reminder(self, user: User, at: time, timezone: str | None = None) -> User:
        tz = timezone or user.timezone or self._content.default_timezone
        await self._users.set_reminder(user.id, at, tz)
        await self._events.add(
            EventType.REMINDER_TIME_SET,
            user_id=user.id,
            payload={"time": at.strftime("%H:%M"), "timezone": tz},
        )
        user.reminder_time = at
        user.timezone = tz
        return user

    def default_reminder_time(self) -> time:
        hours, minutes = self._content.default_reminder_time.split(":")
        return time(hour=int(hours), minute=int(minutes))
