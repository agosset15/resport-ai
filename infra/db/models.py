"""ORM-модели. Один-в-один с ERD (03_erd.puml)."""

from __future__ import annotations

import uuid
from datetime import date as date_type, datetime, time as time_type
from enum import Enum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.domain.enums import (
    AnswerSource,
    Feeling,
    LlmTask,
    Outcome,
    PlanStatus,
    SessionStatus,
    Sport,
)
from infra.db.base import Base


def _values(enum_cls: type[Enum]) -> list[str]:
    return [str(item.value) for item in enum_cls]


sport_enum = SAEnum(Sport, name="sport_enum", values_callable=_values)
session_status_enum = SAEnum(SessionStatus, name="session_status", values_callable=_values)
outcome_enum = SAEnum(Outcome, name="outcome_enum", values_callable=_values)
plan_status_enum = SAEnum(PlanStatus, name="plan_status", values_callable=_values)
feeling_enum = SAEnum(Feeling, name="feeling_enum", values_callable=_values)
answer_source_enum = SAEnum(AnswerSource, name="answer_source", values_callable=_values)
llm_task_enum = SAEnum(LlmTask, name="llm_task_enum", values_callable=_values)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    locale: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    consent_version: Mapped[str | None] = mapped_column(String(32))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_time: Mapped[time_type | None] = mapped_column(Time(timezone=False))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sessions: Mapped[list[SessionModel]] = relationship(back_populates="user")


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    sport: Mapped[Sport] = mapped_column(sport_enum, nullable=False)
    scenario_id: Mapped[str | None] = mapped_column(String(128))
    scenario_version: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[SessionStatus] = mapped_column(
        session_status_enum, default=SessionStatus.IN_PROGRESS, nullable=False
    )
    complaint_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[UserModel] = relationship(back_populates="sessions")
    answers: Mapped[list[SessionAnswerModel]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_sessions_user_status", "user_id", "status"),)


class SessionAnswerModel(Base):
    __tablename__ = "session_answers"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    question_key: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    option_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[AnswerSource] = mapped_column(answer_source_enum, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[SessionModel] = relationship(back_populates="answers")

    __table_args__ = (
        UniqueConstraint("session_id", "question_key", name="uq_answer_per_question"),
    )


class TriageResultModel(Base):
    __tablename__ = "triage_results"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    outcome: Mapped[Outcome] = mapped_column(outcome_enum, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    triggered_flags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    explanation_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RecoveryPlanModel(Base):
    __tablename__ = "recovery_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    plan_key: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    current_stage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[PlanStatus] = mapped_column(
        plan_status_enum, default=PlanStatus.ACTIVE, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    checkins: Mapped[list[CheckinModel]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_plans_status", "status"),)


class CheckinModel(Base):
    __tablename__ = "checkins"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("recovery_plans.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    feeling: Mapped[Feeling] = mapped_column(feeling_enum, nullable=False)
    tasks_done: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    plan: Mapped[RecoveryPlanModel] = relationship(back_populates="checkins")

    __table_args__ = (UniqueConstraint("plan_id", "date", name="uq_checkin_per_day"),)


class LlmCallModel(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL")
    )
    task: Mapped[LlmTask] = mapped_column(llm_task_enum, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    request: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    valid: Mapped[bool] = mapped_column(nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EventModel(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL")
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (Index("ix_events_type_created", "type", "created_at"),)
