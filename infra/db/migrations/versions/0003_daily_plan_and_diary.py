"""Ежедневный план, дневник самочувствия и история версий плана

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None

PLAN_SOURCE = postgresql.ENUM("scenario", "prescription", name="plan_source", create_type=False)
ITEM_KIND = postgresql.ENUM("exercise", "task", "supplement", name="item_kind", create_type=False)
ITEM_STATUS = postgresql.ENUM("done", "partial", "skipped", name="item_status", create_type=False)
SWELLING = postgresql.ENUM(
    "none", "mild", "moderate", "severe", name="swelling_enum", create_type=False
)
DAILY_CAPACITY = postgresql.ENUM(
    "full", "limited", "minimal", name="daily_capacity", create_type=False
)

ENUMS = (PLAN_SOURCE, ITEM_KIND, ITEM_STATUS, SWELLING, DAILY_CAPACITY)

#: Набор llm_task_enum до добавления parse_prescription — нужен для откатa.
LLM_TASK_WITHOUT_PRESCRIPTION = (
    "classify_complaint",
    "normalize_answer",
    "explain_step",
    "classify_body_part",
)


def upgrade() -> None:
    # Новое значение enum нельзя использовать в той же транзакции.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE llm_task_enum ADD VALUE IF NOT EXISTS 'parse_prescription'")

    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    # Источник плана и его версия: пересчёт прогресса считается по текущей версии,
    # а история нужна, чтобы пересчёт можно было объяснить пользователю.
    op.add_column(
        "recovery_plans",
        sa.Column("source", PLAN_SOURCE, nullable=False, server_default="scenario"),
    )
    op.add_column(
        "recovery_plans",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.create_table(
        "plan_item_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recovery_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("item_kind", ITEM_KIND, nullable=False),
        sa.Column("item_key", sa.String(64), nullable=False),
        sa.Column("status", ITEM_STATUS, nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("plan_id", "date", "item_kind", "item_key", name="uq_item_per_day"),
    )
    op.create_index("ix_plan_items_plan_date", "plan_item_logs", ["plan_id", "date"])

    op.create_table(
        "wellbeing_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recovery_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("pain_0_10", sa.Integer(), nullable=False),
        sa.Column("swelling", SWELLING, nullable=False),
        sa.Column("daily_capacity", DAILY_CAPACITY, nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("plan_id", "date", name="uq_wellbeing_per_day"),
    )

    op.create_table(
        "plan_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recovery_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("plan_id", "version", name="uq_plan_version"),
    )


def downgrade() -> None:
    op.execute("DELETE FROM llm_calls WHERE task = 'parse_prescription'")
    kept = ", ".join(f"'{label}'" for label in LLM_TASK_WITHOUT_PRESCRIPTION)
    op.execute(f"CREATE TYPE llm_task_enum_old AS ENUM ({kept})")
    op.execute(
        "ALTER TABLE llm_calls ALTER COLUMN task "
        "TYPE llm_task_enum_old USING task::text::llm_task_enum_old"
    )
    op.execute("DROP TYPE llm_task_enum")
    op.execute("ALTER TYPE llm_task_enum_old RENAME TO llm_task_enum")

    op.drop_table("plan_revisions")
    op.drop_table("wellbeing_logs")
    op.drop_index("ix_plan_items_plan_date", table_name="plan_item_logs")
    op.drop_table("plan_item_logs")
    op.drop_column("recovery_plans", "version")
    op.drop_column("recovery_plans", "source")

    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=True)
