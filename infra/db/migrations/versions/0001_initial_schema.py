"""Начальная схема ReSport AI

Revision ID: 0001
Revises:
Create Date: 2026-09-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None

SPORT = postgresql.ENUM("football", "basketball", name="sport_enum", create_type=False)
SESSION_STATUS = postgresql.ENUM(
    "in_progress",
    "referred",
    "plan_active",
    "completed",
    "abandoned",
    name="session_status",
    create_type=False,
)
OUTCOME = postgresql.ENUM(
    "refer_specialist", "recovery_plan", name="outcome_enum", create_type=False
)
PLAN_STATUS = postgresql.ENUM(
    "active", "completed", "escalated", "dropped", name="plan_status", create_type=False
)
FEELING = postgresql.ENUM("better", "same", "worse", name="feeling_enum", create_type=False)
ANSWER_SOURCE = postgresql.ENUM("button", "llm", "manual", name="answer_source", create_type=False)
LLM_TASK = postgresql.ENUM(
    "classify_complaint",
    "normalize_answer",
    "explain_step",
    name="llm_task_enum",
    create_type=False,
)

ENUMS = (SPORT, SESSION_STATUS, OUTCOME, PLAN_STATUS, FEELING, ANSWER_SOURCE, LLM_TASK)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tg_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64)),
        sa.Column("locale", sa.String(8), nullable=False, server_default="ru"),
        sa.Column("consent_version", sa.String(32)),
        sa.Column("consent_at", sa.DateTime(timezone=True)),
        sa.Column("reminder_time", sa.Time()),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Moscow"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tg_id", name="uq_users_tg_id"),
    )
    op.create_index("ix_users_tg_id", "users", ["tg_id"])

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sport", SPORT, nullable=False),
        sa.Column("scenario_id", sa.String(128)),
        sa.Column("scenario_version", sa.Integer()),
        sa.Column("status", SESSION_STATUS, nullable=False, server_default="in_progress"),
        sa.Column("complaint_text", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_sessions_user_status", "sessions", ["user_id", "status"])

    op.create_table(
        "session_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_key", sa.String(64), nullable=False),
        sa.Column("raw_text", sa.Text()),
        sa.Column("option_id", sa.String(64), nullable=False),
        sa.Column("source", ANSWER_SOURCE, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_session_answers_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("session_id", "question_key", name="uq_answer_per_question"),
    )

    op.create_table(
        "triage_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("outcome", OUTCOME, nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("triggered_flags", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("explanation_text", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_triage_results_session_id_sessions",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "recovery_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("plan_key", sa.String(64), nullable=False),
        sa.Column("plan_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("current_stage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_started_at", sa.DateTime(timezone=True)),
        sa.Column("status", PLAN_STATUS, nullable=False, server_default="active"),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_recovery_plans_session_id_sessions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_plans_status", "recovery_plans", ["status"])

    op.create_table(
        "checkins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("stage_index", sa.Integer(), nullable=False),
        sa.Column("feeling", FEELING, nullable=False),
        sa.Column("tasks_done", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["recovery_plans.id"],
            name="fk_checkins_plan_id_recovery_plans",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("plan_id", "date", name="uq_checkin_per_day"),
    )

    op.create_table(
        "llm_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True)),
        sa.Column("task", LLM_TASK, nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_hash", sa.String(64)),
        sa.Column("request", postgresql.JSONB()),
        sa.Column("response", postgresql.JSONB()),
        sa.Column("valid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text()),
        sa.Column("tokens_in", sa.Integer()),
        sa.Column("tokens_out", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_llm_calls_session_id_sessions",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_llm_calls_prompt_hash", "llm_calls", ["prompt_hash"])

    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("session_id", postgresql.UUID(as_uuid=True)),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_events_user_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_events_session_id_sessions",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_events_type", "events", ["type"])
    op.create_index("ix_events_created_at", "events", ["created_at"])
    op.create_index("ix_events_type_created", "events", ["type", "created_at"])


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("llm_calls")
    op.drop_table("checkins")
    op.drop_table("recovery_plans")
    op.drop_table("triage_results")
    op.drop_table("session_answers")
    op.drop_table("sessions")
    op.drop_table("users")
    bind = op.get_bind()
    for enum in ENUMS:
        enum.drop(bind, checkfirst=True)
