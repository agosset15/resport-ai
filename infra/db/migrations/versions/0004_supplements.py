"""БАДы: анкета, курсы приёма и нежелательные реакции

Отметок приёма здесь нет намеренно: они живут в plan_item_logs с item_kind =
'supplement'. Отдельная таблица была бы дублированием, а исключение БАДов из процента
прохождения программы уже реализовано в core/services/progress.py.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None

SUPPLEMENT_STATUS = postgresql.ENUM(
    "active", "declined", "stopped", name="supplement_status", create_type=False
)
REACTION_SEVERITY = postgresql.ENUM("mild", "severe", name="reaction_severity", create_type=False)

ENUMS = (SUPPLEMENT_STATUS, REACTION_SEVERITY)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "supplement_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "supplement_intakes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("supplement_id", sa.String(64), nullable=False),
        sa.Column("status", SUPPLEMENT_STATUS, nullable=False, server_default="active"),
        sa.Column(
            "include_in_report", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "supplement_id", name="uq_intake_per_supplement"),
    )
    op.create_index("ix_intakes_user_status", "supplement_intakes", ["user_id", "status"])

    op.create_table(
        "adverse_reactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("supplement_id", sa.String(64), nullable=False),
        sa.Column("severity", REACTION_SEVERITY, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_reactions_user", "adverse_reactions", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reactions_user", table_name="adverse_reactions")
    op.drop_table("adverse_reactions")
    op.drop_index("ix_intakes_user_status", table_name="supplement_intakes")
    op.drop_table("supplement_intakes")
    op.drop_table("supplement_profiles")

    bind = op.get_bind()
    for enum in reversed(ENUMS):
        enum.drop(bind, checkfirst=True)
