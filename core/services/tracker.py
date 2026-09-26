"""Трекер восстановления: этапы, чек-ины, переходы и эскалация.

Эскалация — обязательная часть. Если два чек-ина подряд «хуже», план останавливается
и пользователь отправляется к специалисту, даже если этапы ещё не пройдены.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.domain.entities import Checkin, RecoveryPlan, Session, TriageResult, User
from core.domain.enums import EventType, Feeling, Outcome, PlanStatus, SessionStatus
from core.domain.scenario import Plan, Scenario
from core.scenarios.plan_engine import TrackerAction, decide
from core.scenarios.snapshot import plan_from_snapshot, plan_to_snapshot, snapshot_text
from core.services.dto import CheckinResult, PlanProgress, StageView
from core.services.protocols import (
    CheckinRepository,
    EventRepository,
    PlanRepository,
    SessionRepository,
    TriageRepository,
)
from infra.telemetry import get_logger

log = get_logger("services.tracker")


def local_today(timezone: str | None) -> date:
    """«Сегодня» в таймзоне пользователя: чек-ин в 00:20 по Москве — это новый день."""
    if timezone:
        try:
            return datetime.now(ZoneInfo(timezone)).date()
        except (ZoneInfoNotFoundError, ValueError):
            log.warning("tracker.bad_timezone", timezone=timezone)
    return datetime.now(UTC).date()


class TrackerService:
    def __init__(
        self,
        plans: PlanRepository,
        checkins: CheckinRepository,
        sessions: SessionRepository,
        triage: TriageRepository,
        events: EventRepository,
    ) -> None:
        self._plans = plans
        self._checkins = checkins
        self._sessions = sessions
        self._triage = triage
        self._events = events

    # --- выдача плана ---------------------------------------------------------

    async def start_plan(
        self, session: Session, scenario: Scenario, plan_key: str
    ) -> tuple[RecoveryPlan, StageView]:
        plan_def = scenario.plans[plan_key]
        snapshot = plan_to_snapshot(scenario, plan_def)
        plan = await self._plans.create(session_id=session.id, plan_key=plan_key, snapshot=snapshot)
        session.status = SessionStatus.PLAN_ACTIVE
        await self._sessions.update(session)
        await self._events.add(
            EventType.PLAN_STARTED,
            user_id=session.user_id,
            session_id=session.id,
            payload={
                "plan_key": plan_key,
                "scenario_id": scenario.id,
                "scenario_version": scenario.version,
            },
        )
        return plan, self.stage_view(plan)

    # --- отображение ----------------------------------------------------------

    def plan_of(self, plan: RecoveryPlan) -> Plan:
        """План берётся из снимка, а не из текущего YAML."""
        return plan_from_snapshot(plan.plan_snapshot)

    def stage_view(
        self,
        plan: RecoveryPlan,
        *,
        done_today: tuple[str, ...] = (),
        checkin_done: bool = False,
        timezone: str | None = None,
    ) -> StageView:
        definition = self.plan_of(plan)
        index = min(plan.current_stage, len(definition.stages) - 1)
        stage = definition.stages[index]
        started = plan.stage_started_at or plan.started_at or datetime.now(UTC)
        day = (local_today(timezone) - started.date()).days + 1
        return StageView(
            plan_id=plan.id,
            plan_title=definition.title,
            stage_index=index,
            stage_total=len(definition.stages),
            stage_key=stage.key,
            stage_title=stage.title,
            stage_description=stage.description,
            day_number=max(1, min(day, stage.days)),
            day_total=stage.days,
            tasks=stage.tasks,
            done_today=done_today,
            checkin_done_today=checkin_done,
        )

    async def today_view(
        self, plan: RecoveryPlan, day: date | None = None, timezone: str | None = None
    ) -> StageView:
        day = day or local_today(timezone)
        existing = await self._checkins.get_for_date(plan.id, day)
        return self.stage_view(
            plan,
            done_today=tuple(existing.tasks_done) if existing else (),
            checkin_done=existing is not None,
            timezone=timezone,
        )

    async def active_plan(self, user: User) -> RecoveryPlan | None:
        return await self._plans.get_active_for_user(user.id)

    async def progress(self, plan: RecoveryPlan) -> PlanProgress:
        definition = self.plan_of(plan)
        history = await self._checkins.recent(plan.id, plan.current_stage, limit=30)
        return PlanProgress(
            plan_id=plan.id,
            plan_title=definition.title,
            stage_index=plan.current_stage,
            stage_total=len(definition.stages),
            checkins=tuple((c.date, c.feeling) for c in sorted(history, key=lambda c: c.date)),
        )

    # --- чек-ин ---------------------------------------------------------------

    async def submit_checkin(
        self,
        plan: RecoveryPlan,
        *,
        feeling: Feeling,
        tasks_done: list[str],
        note: str | None = None,
        day: date | None = None,
        timezone: str | None = None,
    ) -> CheckinResult:
        day = day or local_today(timezone)
        definition = self.plan_of(plan)

        existing = await self._checkins.get_for_date(plan.id, day)
        if existing is None:
            await self._checkins.add(
                Checkin(
                    plan_id=plan.id,
                    date=day,
                    stage_index=plan.current_stage,
                    feeling=feeling,
                    tasks_done=tasks_done,
                    note=note,
                )
            )

        session = await self._sessions.get(plan.session_id)
        user_id = session.user_id if session else None
        await self._events.add(
            EventType.CHECKIN_SUBMITTED,
            user_id=user_id,
            session_id=plan.session_id,
            payload={
                "plan_id": str(plan.id),
                "stage_index": plan.current_stage,
                "feeling": feeling.value,
                "tasks_done": len(tasks_done),
            },
        )

        stage_checkins = await self._checkins.recent(plan.id, plan.current_stage, limit=14)
        all_checkins = await self._checkins.recent_any(plan.id, limit=14)
        started = plan.stage_started_at or plan.started_at or datetime.now(UTC)
        days_on_stage = (day - started.date()).days + 1

        decision = decide(
            definition,
            min(plan.current_stage, len(definition.stages) - 1),
            stage_checkins=list(stage_checkins),
            all_checkins=list(all_checkins),
            days_on_stage=days_on_stage,
        )

        if decision.action is TrackerAction.ESCALATE:
            return await self._escalate(plan, session, decision.reason)
        if decision.action is TrackerAction.COMPLETE:
            return await self._complete(plan, session, definition)
        if decision.action is TrackerAction.ADVANCE:
            return await self._advance(plan, session, definition, decision.next_stage_index or 0)

        return CheckinResult(
            action=TrackerAction.STAY,
            text="Отметил. Продолжаем по текущему этапу.",
            stage=await self.today_view(plan, day, timezone),
        )

    # --- переходы -------------------------------------------------------------

    async def _advance(
        self, plan: RecoveryPlan, session: Session | None, definition: Plan, next_index: int
    ) -> CheckinResult:
        plan.current_stage = next_index
        plan.stage_started_at = datetime.now(UTC)
        await self._plans.update(plan)
        await self._events.add(
            EventType.STAGE_ADVANCED,
            user_id=session.user_id if session else None,
            session_id=plan.session_id,
            payload={"plan_id": str(plan.id), "stage_index": next_index},
        )
        stage = definition.stages[next_index]
        return CheckinResult(
            action=TrackerAction.ADVANCE,
            text=f"Переходим к следующему этапу: «{stage.title}».",
            stage=self.stage_view(plan),
        )

    async def _complete(
        self, plan: RecoveryPlan, session: Session | None, definition: Plan
    ) -> CheckinResult:
        now = datetime.now(UTC)
        plan.status = PlanStatus.COMPLETED
        plan.finished_at = now
        await self._plans.update(plan)
        if session is not None:
            session.status = SessionStatus.COMPLETED
            session.finished_at = now
            await self._sessions.update(session)
        await self._events.add(
            EventType.PLAN_COMPLETED,
            user_id=session.user_id if session else None,
            session_id=plan.session_id,
            payload={"plan_id": str(plan.id)},
        )
        return CheckinResult(
            action=TrackerAction.COMPLETE,
            text=definition.completion_text,
            completed=True,
        )

    async def _escalate(
        self, plan: RecoveryPlan, session: Session | None, reason: str
    ) -> CheckinResult:
        now = datetime.now(UTC)
        plan.status = PlanStatus.ESCALATED
        plan.finished_at = now
        await self._plans.update(plan)

        if session is not None:
            session.status = SessionStatus.REFERRED
            session.finished_at = now
            await self._sessions.update(session)
            await self._triage.upsert(
                TriageResult(
                    session_id=session.id,
                    outcome=Outcome.REFER_SPECIALIST,
                    reason_codes=["tracker_escalation", reason],
                    triggered_flags=[],
                    explanation_text=snapshot_text(plan.plan_snapshot, "escalation"),
                )
            )

        await self._events.add(
            EventType.PLAN_ESCALATED,
            user_id=session.user_id if session else None,
            session_id=plan.session_id,
            payload={"plan_id": str(plan.id), "reason": reason},
        )
        log.info("tracker.escalated", plan_id=str(plan.id), reason=reason)

        return CheckinResult(
            action=TrackerAction.ESCALATE,
            text=snapshot_text(
                plan.plan_snapshot,
                "escalation",
                "Самочувствие ухудшается. Продолжать план не стоит — нужен очный осмотр.",
            ),
            escalated=True,
        )

    async def drop_plan(self, plan: RecoveryPlan) -> None:
        plan.status = PlanStatus.DROPPED
        plan.finished_at = datetime.now(UTC)
        await self._plans.update(plan)

    async def get_plan(self, plan_id: UUID) -> RecoveryPlan | None:
        return await self._plans.get(plan_id)
