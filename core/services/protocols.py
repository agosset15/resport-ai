"""Порты для сервисов. Реализации живут в infra — core про них не знает."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time
from typing import Any, Protocol
from uuid import UUID

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


class UserRepository(Protocol):
    async def get_by_tg_id(self, tg_id: int) -> User | None: ...

    async def get(self, user_id: UUID) -> User | None: ...

    async def create(self, tg_id: int, username: str | None, locale: str) -> User: ...

    async def set_consent(self, user_id: UUID, version: str, at: datetime) -> None: ...

    async def set_reminder(self, user_id: UUID, at: time, timezone: str) -> None: ...

    async def list_with_reminder_at(self, at: time) -> Sequence[User]: ...


class SessionRepository(Protocol):
    async def create(self, user_id: UUID, sport: Sport) -> Session: ...

    async def get(self, session_id: UUID) -> Session | None: ...

    async def get_active(self, user_id: UUID) -> Session | None: ...

    async def update(self, session: Session) -> None: ...

    async def abandon_active(self, user_id: UUID) -> None: ...

    async def set_status(
        self, session_id: UUID, status: SessionStatus, finished_at: datetime | None = None
    ) -> None: ...

    async def upsert_answer(self, answer: Answer) -> None: ...

    async def answers(self, session_id: UUID) -> Sequence[Answer]: ...

    async def answers_map(self, session_id: UUID) -> dict[str, str]: ...


class TriageRepository(Protocol):
    async def upsert(self, result: TriageResult) -> TriageResult: ...

    async def get(self, session_id: UUID) -> TriageResult | None: ...


class PlanRepository(Protocol):
    async def create(
        self, session_id: UUID, plan_key: str, snapshot: dict[str, Any]
    ) -> RecoveryPlan: ...

    async def get(self, plan_id: UUID) -> RecoveryPlan | None: ...

    async def get_active_for_user(self, user_id: UUID) -> RecoveryPlan | None: ...

    async def update(self, plan: RecoveryPlan) -> None: ...

    async def set_status(
        self, plan_id: UUID, status: PlanStatus, finished_at: datetime | None = None
    ) -> None: ...

    async def list_active(self) -> Sequence[tuple[RecoveryPlan, User]]: ...


class CheckinRepository(Protocol):
    async def add(self, checkin: Checkin) -> Checkin: ...

    async def get_for_date(self, plan_id: UUID, day: date) -> Checkin | None: ...

    async def recent(self, plan_id: UUID, stage_index: int, limit: int) -> Sequence[Checkin]: ...

    async def recent_any(self, plan_id: UUID, limit: int) -> Sequence[Checkin]: ...

    async def count_for_stage(self, plan_id: UUID, stage_index: int) -> int: ...

    async def last_feelings(self, plan_id: UUID, limit: int) -> Sequence[Feeling]: ...


class LlmCallRepository(Protocol):
    async def add(
        self,
        *,
        task: LlmTask,
        model: str,
        session_id: UUID | None,
        prompt_hash: str | None,
        request: dict[str, Any] | None,
        response: dict[str, Any] | None,
        valid: bool,
        error: str | None,
        tokens_in: int | None,
        tokens_out: int | None,
        latency_ms: int | None,
    ) -> None: ...


class EventRepository(Protocol):
    async def add(
        self,
        event_type: EventType,
        *,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None: ...


class UnitOfWork(Protocol):
    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
