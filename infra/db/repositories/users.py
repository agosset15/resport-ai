from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, time
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities import User
from infra.db.models import UserModel
from infra.db.repositories.mappers import to_user


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_tg_id(self, tg_id: int) -> User | None:
        model = await self._session.scalar(select(UserModel).where(UserModel.tg_id == tg_id))
        return to_user(model) if model else None

    async def get(self, user_id: UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return to_user(model) if model else None

    async def create(self, tg_id: int, username: str | None, locale: str) -> User:
        model = UserModel(tg_id=tg_id, username=username, locale=locale)
        self._session.add(model)
        await self._session.flush()
        return to_user(model)

    async def set_consent(self, user_id: UUID, version: str, at: datetime) -> None:
        await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(consent_version=version, consent_at=at)
        )

    async def set_reminder(self, user_id: UUID, at: time, timezone: str) -> None:
        await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(reminder_time=at, timezone=timezone)
        )

    async def list_with_reminder_at(self, at: time) -> Sequence[User]:
        models = await self._session.scalars(select(UserModel).where(UserModel.reminder_time == at))
        return [to_user(m) for m in models]
