"""Сущности домена. Репозитории отдают и принимают именно их, а не ORM-модели."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from core.domain.enums import (
    AnswerSource,
    Feeling,
    Outcome,
    PlanStatus,
    SessionStatus,
    Sport,
)


@dataclass(slots=True)
class User:
    id: UUID
    tg_id: int
    username: str | None = None
    locale: str = "ru"
    consent_version: str | None = None
    consent_at: datetime | None = None
    reminder_time: time | None = None
    timezone: str = "Europe/Moscow"
    created_at: datetime | None = None

    def has_consent(self, required_version: str) -> bool:
        return self.consent_version == required_version


@dataclass(slots=True)
class Session:
    id: UUID
    user_id: UUID
    sport: Sport
    status: SessionStatus = SessionStatus.IN_PROGRESS
    scenario_id: str | None = None
    scenario_version: int | None = None
    complaint_text: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(slots=True)
class Answer:
    session_id: UUID
    question_key: str
    option_id: str
    source: AnswerSource
    raw_text: str | None = None
    id: UUID | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class TriageResult:
    session_id: UUID
    outcome: Outcome
    reason_codes: list[str] = field(default_factory=list)
    triggered_flags: list[str] = field(default_factory=list)
    explanation_text: str | None = None
    id: UUID | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class RecoveryPlan:
    id: UUID
    session_id: UUID
    plan_key: str
    plan_snapshot: dict[str, Any]
    current_stage: int = 0
    status: PlanStatus = PlanStatus.ACTIVE
    stage_started_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(slots=True)
class Checkin:
    plan_id: UUID
    date: date
    stage_index: int
    feeling: Feeling
    tasks_done: list[str] = field(default_factory=list)
    note: str | None = None
    id: UUID | None = None
    created_at: datetime | None = None
