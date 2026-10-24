"""Чтение дневника и прогресса: собирает данные из репозиториев для чистого расчёта.

Сам расчёт живёт в `core/services/progress.py` и ничего не знает про БД.
"""

from __future__ import annotations

from datetime import date, timedelta

from core.domain.entities import RecoveryPlan
from core.domain.enums import EventType, PlanStatus
from core.scenarios.snapshot import plan_from_snapshot
from core.services.progress import ProgressView, build_progress
from core.services.protocols import (
    EventRepository,
    PlanItemRepository,
    PlanRevisionRepository,
    SessionRepository,
    WellbeingRepository,
)
from core.services.tracker import local_today


class DiaryService:
    def __init__(
        self,
        items: PlanItemRepository,
        wellbeing: WellbeingRepository,
        revisions: PlanRevisionRepository,
        sessions: SessionRepository,
        events: EventRepository,
    ) -> None:
        self._items = items
        self._wellbeing = wellbeing
        self._revisions = revisions
        self._sessions = sessions
        self._events = events

    async def progress(self, plan: RecoveryPlan, timezone: str | None = None) -> ProgressView:
        today = local_today(timezone)
        definition = plan_from_snapshot(plan.plan_snapshot)
        started = plan.started_at.date() if plan.started_at else today
        stage_started = plan.stage_started_at.date() if plan.stage_started_at else started

        view = build_progress(
            definition,
            stage_index=plan.current_stage,
            item_logs=await self._items.for_plan(plan.id),
            wellbeing_logs=await self._wellbeing.for_plan(plan.id),
            started_on=started,
            today=today,
            stage_started_on=stage_started,
            completed=plan.status is PlanStatus.COMPLETED,
        )

        session = await self._sessions.get(plan.session_id)
        await self._events.add(
            EventType.PROGRESS_VIEWED,
            user_id=session.user_id if session else None,
            session_id=plan.session_id,
            payload={"plan_id": str(plan.id), "percent": view.percent},
        )
        return view

    async def period(
        self, plan: RecoveryPlan, days: int = 14, timezone: str | None = None
    ) -> tuple[date, date]:
        end = local_today(timezone)
        return end - timedelta(days=days - 1), end

    async def revision_count(self, plan: RecoveryPlan) -> int:
        """Сколько раз план менялся: при пересчёте прогресса это нужно пояснить."""
        return len(await self._revisions.for_plan(plan.id))
