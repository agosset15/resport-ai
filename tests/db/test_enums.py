"""Нативные enum в Postgres должны совпадать с перечислениями домена.

`values_callable=_values` в `infra/db/models.py` берёт метки из Python-enum, поэтому
добавленное в код и забытое в миграции значение проявится только при вставке — и уже
на проде. Этот тест ловит расхождение заранее.

Требует поднятую Postgres с применёнными миграциями:
    docker compose up -d postgres && uv run alembic upgrade head && uv run pytest tests/db
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.domain.enums import (
    AnswerSource,
    DailyCapacity,
    Feeling,
    ItemKind,
    ItemStatus,
    LlmTask,
    Outcome,
    PlanSource,
    PlanStatus,
    ReactionSeverity,
    SessionStatus,
    Sport,
    SupplementStatus,
    Swelling,
)
from infra.db.engine import build_engine, build_session_factory

pytestmark = pytest.mark.db

ENUM_TYPES = (
    ("sport_enum", Sport),
    ("session_status", SessionStatus),
    ("outcome_enum", Outcome),
    ("plan_status", PlanStatus),
    ("feeling_enum", Feeling),
    ("answer_source", AnswerSource),
    ("llm_task_enum", LlmTask),
    ("plan_source", PlanSource),
    ("item_kind", ItemKind),
    ("item_status", ItemStatus),
    ("swelling_enum", Swelling),
    ("daily_capacity", DailyCapacity),
    ("supplement_status", SupplementStatus),
    ("reaction_severity", ReactionSeverity),
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = build_engine(get_settings().db)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — нет БД: тест не про это
        await engine.dispose()
        pytest.skip(f"Postgres недоступна: {exc}")

    factory = build_session_factory(engine)
    async with factory() as db_session:
        yield db_session
        await db_session.rollback()
    await engine.dispose()


@pytest.mark.parametrize(("type_name", "enum_cls"), ENUM_TYPES)
async def test_db_enum_matches_domain(
    session: AsyncSession, type_name: str, enum_cls: type
) -> None:
    rows = await session.execute(
        text(
            "SELECT e.enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = :name ORDER BY e.enumsortorder"
        ),
        {"name": type_name},
    )
    in_db = [row[0] for row in rows]
    in_code = [item.value for item in enum_cls]
    assert in_db, f"тип {type_name} не найден в базе — миграции применены?"
    assert set(in_db) == set(in_code), (
        f"{type_name}: в базе {sorted(in_db)}, в коде {sorted(in_code)} — не хватает миграции"
    )


#: Приведение типа пишем через CAST, а не через `::`: в `text()` двоеточие — это
#: маркер bind-параметра, поэтому `:value::outcome_enum` вообще не распознаётся как
#: параметр и в Postgres уезжает литеральная строка с двоеточиями.
CAST_SQL = "SELECT CAST(:value AS {type_name})"


async def test_self_rehab_outcome_is_storable(session: AsyncSession) -> None:
    """Миграция 0002 добавила значение, и оно действительно принимается колонкой."""
    result = await session.execute(
        text(CAST_SQL.format(type_name="outcome_enum")),
        {"value": Outcome.SELF_REHAB.value},
    )
    assert result.scalar() == Outcome.SELF_REHAB.value


async def test_classify_body_part_task_is_storable(session: AsyncSession) -> None:
    result = await session.execute(
        text(CAST_SQL.format(type_name="llm_task_enum")),
        {"value": LlmTask.CLASSIFY_BODY_PART.value},
    )
    assert result.scalar() == LlmTask.CLASSIFY_BODY_PART.value


async def test_parse_prescription_task_is_storable(session: AsyncSession) -> None:
    """Значение добавлено миграцией 0003 — без него разбор назначения не запишется."""
    result = await session.execute(
        text(CAST_SQL.format(type_name="llm_task_enum")),
        {"value": LlmTask.PARSE_PRESCRIPTION.value},
    )
    assert result.scalar() == LlmTask.PARSE_PRESCRIPTION.value


async def test_supplement_enums_are_storable(session: AsyncSession) -> None:
    """Миграция 0004: статус курса и тяжесть реакции."""
    for type_name, value in (
        ("supplement_status", SupplementStatus.ACTIVE.value),
        ("reaction_severity", ReactionSeverity.SEVERE.value),
        ("item_kind", ItemKind.SUPPLEMENT.value),
    ):
        result = await session.execute(text(CAST_SQL.format(type_name=type_name)), {"value": value})
        assert result.scalar() == value
