from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities import Checkin, RecoveryPlan, User
from core.domain.enums import Feeling, PlanStatus
from infra.db.models import CheckinModel, RecoveryPlanModel, SessionModel, UserModel
from infra.db.repositories.mappers import to_checkin, to_plan, to_user


class SqlPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, session_id: UUID, plan_key: str, snapshot: dict[str, Any]
    ) -> RecoveryPlan:
        model = RecoveryPlanModel(
            session_id=session_id,
            plan_key=plan_key,
            plan_snapshot=snapshot,
            current_stage=0,
            status=PlanStatus.ACTIVE,
            stage_started_at=datetime.now(),
        )
        self._session.add(model)
        await self._session.flush()
        return to_plan(model)

    async def get(self, plan_id: UUID) -> RecoveryPlan | None:
        model = await self._session.get(RecoveryPlanModel, plan_id)
        return to_plan(model) if model else None

    async def get_by_session(self, session_id: UUID) -> RecoveryPlan | None:
        model = await self._session.scalar(
            select(RecoveryPlanModel).where(RecoveryPlanModel.session_id == session_id)
        )
        return to_plan(model) if model else None

    async def get_active_for_user(self, user_id: UUID) -> RecoveryPlan | None:
        model = await self._session.scalar(
            select(RecoveryPlanModel)
            .join(SessionModel, SessionModel.id == RecoveryPlanModel.session_id)
            .where(SessionModel.user_id == user_id, RecoveryPlanModel.status == PlanStatus.ACTIVE)
            .order_by(RecoveryPlanModel.started_at.desc())
            .limit(1)
        )
        return to_plan(model) if model else None

    async def update(self, plan: RecoveryPlan) -> None:
        await self._session.execute(
            update(RecoveryPlanModel)
            .where(RecoveryPlanModel.id == plan.id)
            .values(
                current_stage=plan.current_stage,
                stage_started_at=plan.stage_started_at,
                status=plan.status,
                finished_at=plan.finished_at,
            )
        )

    async def set_status(
        self, plan_id: UUID, status: PlanStatus, finished_at: datetime | None = None
    ) -> None:
        await self._session.execute(
            update(RecoveryPlanModel)
            .where(RecoveryPlanModel.id == plan_id)
            .values(status=status, finished_at=finished_at)
        )

    async def list_active(self) -> Sequence[tuple[RecoveryPlan, User]]:
        rows = await self._session.execute(
            select(RecoveryPlanModel, UserModel)
            .join(SessionModel, SessionModel.id == RecoveryPlanModel.session_id)
            .join(UserModel, UserModel.id == SessionModel.user_id)
            .where(RecoveryPlanModel.status == PlanStatus.ACTIVE)
        )
        return [(to_plan(plan), to_user(user)) for plan, user in rows.all()]

    async def user_of_plan(self, plan_id: UUID) -> User | None:
        model = await self._session.scalar(
            select(UserModel)
            .join(SessionModel, SessionModel.user_id == UserModel.id)
            .join(RecoveryPlanModel, RecoveryPlanModel.session_id == SessionModel.id)
            .where(RecoveryPlanModel.id == plan_id)
        )
        return to_user(model) if model else None


class SqlCheckinRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, checkin: Checkin) -> Checkin:
        model = CheckinModel(
            plan_id=checkin.plan_id,
            date=checkin.date,
            stage_index=checkin.stage_index,
            feeling=checkin.feeling,
            tasks_done=checkin.tasks_done,
            note=checkin.note,
        )
        self._session.add(model)
        await self._session.flush()
        return to_checkin(model)

    async def get_for_date(self, plan_id: UUID, day: date) -> Checkin | None:
        model = await self._session.scalar(
            select(CheckinModel).where(CheckinModel.plan_id == plan_id, CheckinModel.date == day)
        )
        return to_checkin(model) if model else None

    async def recent(self, plan_id: UUID, stage_index: int, limit: int) -> Sequence[Checkin]:
        models = await self._session.scalars(
            select(CheckinModel)
            .where(CheckinModel.plan_id == plan_id, CheckinModel.stage_index == stage_index)
            .order_by(CheckinModel.date.desc())
            .limit(limit)
        )
        return [to_checkin(m) for m in models]

    async def recent_any(self, plan_id: UUID, limit: int) -> Sequence[Checkin]:
        """Вся история плана, свежие первыми: эскалация считается сквозь этапы."""
        models = await self._session.scalars(
            select(CheckinModel)
            .where(CheckinModel.plan_id == plan_id)
            .order_by(CheckinModel.date.desc())
            .limit(limit)
        )
        return [to_checkin(m) for m in models]

    async def count_for_stage(self, plan_id: UUID, stage_index: int) -> int:
        total = await self._session.scalar(
            select(func.count())
            .select_from(CheckinModel)
            .where(CheckinModel.plan_id == plan_id, CheckinModel.stage_index == stage_index)
        )
        return int(total or 0)

    async def last_feelings(self, plan_id: UUID, limit: int) -> Sequence[Feeling]:
        rows = await self._session.scalars(
            select(CheckinModel.feeling)
            .where(CheckinModel.plan_id == plan_id)
            .order_by(CheckinModel.date.desc())
            .limit(limit)
        )
        return list(rows)

    async def history(self, plan_id: UUID) -> Sequence[Checkin]:
        models = await self._session.scalars(
            select(CheckinModel).where(CheckinModel.plan_id == plan_id).order_by(CheckinModel.date)
        )
        return [to_checkin(m) for m in models]
