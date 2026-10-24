"""Исход self_rehab и задача classify_body_part

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23
"""

from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None

OUTCOME_OLD = ("refer_specialist", "recovery_plan")
LLM_TASK_OLD = ("classify_complaint", "normalize_answer", "explain_step")


def upgrade() -> None:
    # PostgreSQL разрешает ADD VALUE в транзакции, но новое значение нельзя использовать
    # до коммита. Alembic оборачивает миграцию в одну транзакцию — выходим из неё.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE outcome_enum ADD VALUE IF NOT EXISTS 'self_rehab'")
        op.execute("ALTER TYPE llm_task_enum ADD VALUE IF NOT EXISTS 'classify_body_part'")


def _shrink(type_name: str, keep: tuple[str, ...], table: str, column: str) -> None:
    """Значение из enum удалить нельзя — пересоздаём тип с прежним набором."""
    labels = ", ".join(f"'{label}'" for label in keep)
    op.execute(f"CREATE TYPE {type_name}_old AS ENUM ({labels})")
    op.execute(
        f"ALTER TABLE {table} ALTER COLUMN {column} "
        f"TYPE {type_name}_old USING {column}::text::{type_name}_old"
    )
    op.execute(f"DROP TYPE {type_name}")
    op.execute(f"ALTER TYPE {type_name}_old RENAME TO {type_name}")


def downgrade() -> None:
    # Откат теряет различие между self_rehab и recovery_plan: оба становятся recovery_plan.
    op.execute("UPDATE triage_results SET outcome = 'recovery_plan' WHERE outcome = 'self_rehab'")
    op.execute("DELETE FROM llm_calls WHERE task = 'classify_body_part'")
    _shrink("outcome_enum", OUTCOME_OLD, "triage_results", "outcome")
    _shrink("llm_task_enum", LLM_TASK_OLD, "llm_calls", "task")
