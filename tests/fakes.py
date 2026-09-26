"""Ин-мемори реализации портов. Сервисы тестируются без Postgres и без сети."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time
from typing import Any
from uuid import UUID, uuid4

from core.domain.entities import (
    Answer,
    Checkin,
    RecoveryPlan,
    Session,
    TriageResult,
    User,
)
from core.domain.enums import (
    EventType,
    Feeling,
    LlmTask,
    PlanStatus,
    SessionStatus,
    Sport,
)
from core.llm.provider import LlmResult, LlmUnavailable


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[UUID, User] = {}

    async def get_by_tg_id(self, tg_id: int) -> User | None:
        return next((u for u in self.users.values() if u.tg_id == tg_id), None)

    async def get(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def create(self, tg_id: int, username: str | None, locale: str) -> User:
        user = User(id=uuid4(), tg_id=tg_id, username=username, locale=locale)
        self.users[user.id] = user
        return user

    async def set_consent(self, user_id: UUID, version: str, at: datetime) -> None:
        user = self.users[user_id]
        user.consent_version = version
        user.consent_at = at

    async def set_reminder(self, user_id: UUID, at: time, timezone: str) -> None:
        user = self.users[user_id]
        user.reminder_time = at
        user.timezone = timezone

    async def list_with_reminder_at(self, at: time) -> Sequence[User]:
        return [u for u in self.users.values() if u.reminder_time == at]


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, Session] = {}
        self.answers: dict[UUID, dict[str, Answer]] = {}

    async def create(self, user_id: UUID, sport: Sport) -> Session:
        session = Session(id=uuid4(), user_id=user_id, sport=sport, created_at=datetime.now())
        self.sessions[session.id] = session
        self.answers[session.id] = {}
        return session

    async def get(self, session_id: UUID) -> Session | None:
        return self.sessions.get(session_id)

    async def get_active(self, user_id: UUID) -> Session | None:
        active = [
            s
            for s in self.sessions.values()
            if s.user_id == user_id
            and s.status in (SessionStatus.IN_PROGRESS, SessionStatus.PLAN_ACTIVE)
        ]
        return active[-1] if active else None

    async def update(self, session: Session) -> None:
        self.sessions[session.id] = session

    async def abandon_active(self, user_id: UUID) -> None:
        for session in self.sessions.values():
            if session.user_id == user_id and session.status in (
                SessionStatus.IN_PROGRESS,
                SessionStatus.PLAN_ACTIVE,
            ):
                session.status = SessionStatus.ABANDONED

    async def set_status(
        self, session_id: UUID, status: SessionStatus, finished_at: datetime | None = None
    ) -> None:
        session = self.sessions[session_id]
        session.status = status
        session.finished_at = finished_at

    async def upsert_answer(self, answer: Answer) -> None:
        self.answers.setdefault(answer.session_id, {})[answer.question_key] = answer

    async def answers(self, session_id: UUID) -> Sequence[Answer]:
        return list(self.answers.get(session_id, {}).values())

    async def answers_map(self, session_id: UUID) -> dict[str, str]:
        return {k: a.option_id for k, a in self.answers.get(session_id, {}).items()}


class FakeTriageRepository:
    def __init__(self) -> None:
        self.results: dict[UUID, TriageResult] = {}

    async def upsert(self, result: TriageResult) -> TriageResult:
        result.id = result.id or uuid4()
        self.results[result.session_id] = result
        return result

    async def get(self, session_id: UUID) -> TriageResult | None:
        return self.results.get(session_id)


class FakePlanRepository:
    def __init__(self, sessions: FakeSessionRepository) -> None:
        self.plans: dict[UUID, RecoveryPlan] = {}
        self._sessions = sessions

    async def create(
        self, session_id: UUID, plan_key: str, snapshot: dict[str, Any]
    ) -> RecoveryPlan:
        plan = RecoveryPlan(
            id=uuid4(),
            session_id=session_id,
            plan_key=plan_key,
            plan_snapshot=snapshot,
            stage_started_at=datetime.now(),
            started_at=datetime.now(),
        )
        self.plans[plan.id] = plan
        return plan

    async def get(self, plan_id: UUID) -> RecoveryPlan | None:
        return self.plans.get(plan_id)

    async def get_active_for_user(self, user_id: UUID) -> RecoveryPlan | None:
        for plan in self.plans.values():
            session = self._sessions.sessions.get(plan.session_id)
            if (
                session is not None
                and session.user_id == user_id
                and plan.status is PlanStatus.ACTIVE
            ):
                return plan
        return None

    async def update(self, plan: RecoveryPlan) -> None:
        self.plans[plan.id] = plan

    async def set_status(
        self, plan_id: UUID, status: PlanStatus, finished_at: datetime | None = None
    ) -> None:
        plan = self.plans[plan_id]
        plan.status = status
        plan.finished_at = finished_at

    async def list_active(self) -> Sequence[tuple[RecoveryPlan, User]]:
        return []


class FakeCheckinRepository:
    def __init__(self) -> None:
        self.items: list[Checkin] = []

    async def add(self, checkin: Checkin) -> Checkin:
        checkin.id = uuid4()
        self.items.append(checkin)
        return checkin

    async def get_for_date(self, plan_id: UUID, day: date) -> Checkin | None:
        return next((c for c in self.items if c.plan_id == plan_id and c.date == day), None)

    async def recent(self, plan_id: UUID, stage_index: int, limit: int) -> Sequence[Checkin]:
        items = [c for c in self.items if c.plan_id == plan_id and c.stage_index == stage_index]
        return sorted(items, key=lambda c: c.date, reverse=True)[:limit]

    async def recent_any(self, plan_id: UUID, limit: int) -> Sequence[Checkin]:
        items = [c for c in self.items if c.plan_id == plan_id]
        return sorted(items, key=lambda c: c.date, reverse=True)[:limit]

    async def count_for_stage(self, plan_id: UUID, stage_index: int) -> int:
        return len([c for c in self.items if c.plan_id == plan_id and c.stage_index == stage_index])

    async def last_feelings(self, plan_id: UUID, limit: int) -> Sequence[Feeling]:
        items = sorted(
            (c for c in self.items if c.plan_id == plan_id),
            key=lambda c: c.date,
            reverse=True,
        )
        return [c.feeling for c in items[:limit]]


class FakeEventRepository:
    def __init__(self) -> None:
        self.events: list[tuple[EventType, dict[str, Any]]] = []

    async def add(
        self,
        event_type: EventType,
        *,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.events.append((event_type, payload or {}))

    def types(self) -> list[EventType]:
        return [event for event, _ in self.events]


class FakeLlmCallRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def add(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)

    def valid_count(self) -> int:
        return sum(1 for call in self.calls if call.get("valid"))


class ScriptedLlmProvider:
    """Отдаёт заранее заданные ответы по типу задачи или падает."""

    name = "scripted"

    def __init__(self, responses: dict[str, Any] | None = None, fail: bool = False) -> None:
        self.model = "scripted-1"
        self._responses = responses or {}
        self._fail = fail
        self.calls: list[tuple[str, str]] = []

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 700,
    ) -> LlmResult:
        self.calls.append((system, user))
        if self._fail:
            raise LlmUnavailable("scripted failure")
        key = _guess_task(schema)
        data = self._responses.get(key)
        if data is None:
            raise LlmUnavailable(f"нет заготовленного ответа для {key}")
        return LlmResult(text="", model=self.model, data=data, tokens_in=10, tokens_out=5)

    async def aclose(self) -> None:
        return None


def _guess_task(schema: dict[str, Any] | None) -> str:
    if not schema:
        return "unknown"
    props = set(schema.get("properties", {}))
    if "scenario_id" in props:
        return LlmTask.CLASSIFY_COMPLAINT.value
    if "option_id" in props:
        return LlmTask.NORMALIZE_ANSWER.value
    return LlmTask.EXPLAIN_STEP.value
