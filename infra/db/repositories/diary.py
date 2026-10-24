"""Отметки по пунктам плана, дневник самочувствия и версии плана."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities import PlanItemLog, PlanRevision, WellbeingLog
from infra.db.models import PlanItemLogModel, PlanRevisionModel, WellbeingLogModel
from infra.db.repositories.mappers import to_plan_item_log, to_plan_revision, to_wellbeing_log


class SqlPlanItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, log: PlanItemLog) -> None:
        """Повторная отметка того же пункта за тот же день заменяет прежнюю."""
        statement = (
            insert(PlanItemLogModel)
            .values(
                plan_id=log.plan_id,
                date=log.date,
                item_kind=log.item_kind,
                item_key=log.item_key,
                status=log.status,
                comment=log.comment,
            )
            .on_conflict_do_update(
                constraint="uq_item_per_day",
                set_={"status": log.status, "comment": log.comment},
            )
        )
        await self._session.execute(statement)

    async def for_date(self, plan_id: UUID, day: date) -> Sequence[PlanItemLog]:
        rows = await self._session.scalars(
            select(PlanItemLogModel).where(
                PlanItemLogModel.plan_id == plan_id, PlanItemLogModel.date == day
            )
        )
        return [to_plan_item_log(row) for row in rows]

    async def for_plan(self, plan_id: UUID) -> Sequence[PlanItemLog]:
        rows = await self._session.scalars(
            select(PlanItemLogModel)
            .where(PlanItemLogModel.plan_id == plan_id)
            .order_by(PlanItemLogModel.date)
        )
        return [to_plan_item_log(row) for row in rows]

    async def for_period(self, plan_id: UUID, start: date, end: date) -> Sequence[PlanItemLog]:
        rows = await self._session.scalars(
            select(PlanItemLogModel)
            .where(
                PlanItemLogModel.plan_id == plan_id,
                PlanItemLogModel.date >= start,
                PlanItemLogModel.date <= end,
            )
            .order_by(PlanItemLogModel.date)
        )
        return [to_plan_item_log(row) for row in rows]


class SqlWellbeingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, log: WellbeingLog) -> None:
        statement = (
            insert(WellbeingLogModel)
            .values(
                plan_id=log.plan_id,
                date=log.date,
                pain_0_10=log.pain_0_10,
                swelling=log.swelling,
                daily_capacity=log.daily_capacity,
                note=log.note,
            )
            .on_conflict_do_update(
                constraint="uq_wellbeing_per_day",
                set_={
                    "pain_0_10": log.pain_0_10,
                    "swelling": log.swelling,
                    "daily_capacity": log.daily_capacity,
                    "note": log.note,
                },
            )
        )
        await self._session.execute(statement)

    async def get_for_date(self, plan_id: UUID, day: date) -> WellbeingLog | None:
        model = await self._session.scalar(
            select(WellbeingLogModel).where(
                WellbeingLogModel.plan_id == plan_id, WellbeingLogModel.date == day
            )
        )
        return to_wellbeing_log(model) if model else None

    async def for_plan(self, plan_id: UUID) -> Sequence[WellbeingLog]:
        rows = await self._session.scalars(
            select(WellbeingLogModel)
            .where(WellbeingLogModel.plan_id == plan_id)
            .order_by(WellbeingLogModel.date)
        )
        return [to_wellbeing_log(row) for row in rows]

    async def for_period(self, plan_id: UUID, start: date, end: date) -> Sequence[WellbeingLog]:
        rows = await self._session.scalars(
            select(WellbeingLogModel)
            .where(
                WellbeingLogModel.plan_id == plan_id,
                WellbeingLogModel.date >= start,
                WellbeingLogModel.date <= end,
            )
            .order_by(WellbeingLogModel.date)
        )
        return [to_wellbeing_log(row) for row in rows]


class SqlPlanRevisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, plan_id: UUID, version: int, snapshot: dict[str, Any], reason: str) -> None:
        self._session.add(
            PlanRevisionModel(plan_id=plan_id, version=version, snapshot=snapshot, reason=reason)
        )
        await self._session.flush()

    async def for_plan(self, plan_id: UUID) -> Sequence[PlanRevision]:
        rows = await self._session.scalars(
            select(PlanRevisionModel)
            .where(PlanRevisionModel.plan_id == plan_id)
            .order_by(PlanRevisionModel.version)
        )
        return [to_plan_revision(row) for row in rows]
