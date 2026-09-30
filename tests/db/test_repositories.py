"""Интеграционные тесты репозиториев. Требуют поднятую Postgres.

Пропускаются автоматически, если БД недоступна:
    docker compose up -d postgres && uv run alembic upgrade head && uv run pytest tests/db
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import get_settings
from core.domain.entities import Answer, Checkin, TriageResult
from core.domain.enums import (
    AnswerSource,
    EventType,
    Feeling,
    LlmTask,
    Outcome,
    PlanStatus,
    SessionStatus,
    Sport,
)
from infra.db.engine import build_engine, build_session_factory
from infra.db.repositories.audit import SqlEventRepository, SqlLlmCallRepository
from infra.db.repositories.export import SqlExportRepository
from infra.db.repositories.plans import SqlCheckinRepository, SqlPlanRepository
from infra.db.repositories.sessions import SqlSessionRepository
from infra.db.repositories.triage import SqlTriageRepository
from infra.db.repositories.users import SqlUserRepository

pytestmark = pytest.mark.db


# Результат первой проверки кешируется: без БД каждый коннект стоит секунды,
# а тестов с этой фикстурой много — проверяем доступность один раз за сессию.
_db_unavailable: str | None = None
_db_checked = False


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    global _db_checked, _db_unavailable
    if _db_checked and _db_unavailable is not None:
        pytest.skip(_db_unavailable)

    engine = build_engine(get_settings().db)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — нет БД: тест не про это
        await engine.dispose()
        _db_checked = True
        _db_unavailable = f"Postgres недоступна: {exc}"
        pytest.skip(_db_unavailable)
    _db_checked = True
    _db_unavailable = None

    factory = build_session_factory(engine)
    async with factory() as db_session:
        trans = await db_session.begin_nested() if db_session.in_transaction() else None
        yield db_session
        if trans is not None and trans.is_active:
            await trans.rollback()
        await db_session.rollback()
    await engine.dispose()


def unique_tg_id() -> int:
    return int(datetime.now(UTC).timestamp() * 1_000_000) % 2_000_000_000


class TestRoundTrip:
    async def test_full_path(self, session: AsyncSession) -> None:
        users = SqlUserRepository(session)
        sessions = SqlSessionRepository(session)
        triage = SqlTriageRepository(session)
        plans = SqlPlanRepository(session)
        checkins = SqlCheckinRepository(session)
        events = SqlEventRepository(session)
        llm_calls = SqlLlmCallRepository(session)

        user = await users.create(tg_id=unique_tg_id(), username="int_test", locale="ru")
        await users.set_consent(user.id, "2026-01-15", datetime.now(UTC))
        await users.set_reminder(user.id, time(19, 30), "Europe/Moscow")
        stored_user = await users.get_by_tg_id(user.tg_id)
        assert stored_user is not None
        assert stored_user.consent_version == "2026-01-15"
        assert stored_user.reminder_time == time(19, 30)

        sess = await sessions.create(user.id, Sport.FOOTBALL)
        sess.scenario_id = "football.ankle_sprain"
        sess.scenario_version = 1
        await sessions.update(sess)

        await sessions.upsert_answer(
            Answer(
                session_id=sess.id,
                question_key="q_when",
                option_id="today",
                source=AnswerSource.BUTTON,
            )
        )
        # повторный ответ на тот же вопрос перезаписывает, а не дублирует
        await sessions.upsert_answer(
            Answer(
                session_id=sess.id,
                question_key="q_when",
                option_id="more_week",
                source=AnswerSource.LLM,
                raw_text="недели две назад",
            )
        )
        answers = await sessions.answers(sess.id)
        assert len(answers) == 1
        assert answers[0].option_id == "more_week"
        assert answers[0].source is AnswerSource.LLM
        assert await sessions.answers_map(sess.id) == {"q_when": "more_week"}

        result = await triage.upsert(
            TriageResult(
                session_id=sess.id,
                outcome=Outcome.RECOVERY_PLAN,
                reason_codes=["mild_sprain"],
                triggered_flags=[],
                explanation_text="текст",
            )
        )
        assert result.outcome is Outcome.RECOVERY_PLAN
        rewritten = await triage.upsert(
            TriageResult(
                session_id=sess.id,
                outcome=Outcome.REFER_SPECIALIST,
                reason_codes=["tracker_escalation"],
            )
        )
        assert rewritten.outcome is Outcome.REFER_SPECIALIST

        snapshot = {
            "format": 1,
            "plan_key": "ankle_sprain_basic",
            "title": "План",
            "completion_text": "Готово",
            "scenario_id": "football.ankle_sprain",
            "scenario_version": 1,
            "stages": [],
        }
        plan = await plans.create(sess.id, "ankle_sprain_basic", snapshot)
        assert plan.plan_snapshot["scenario_version"] == 1
        assert await plans.get_active_for_user(user.id) is not None

        today = date.today()
        await checkins.add(
            Checkin(
                plan_id=plan.id,
                date=today,
                stage_index=0,
                feeling=Feeling.WORSE,
                tasks_done=["ice"],
            )
        )
        await checkins.add(
            Checkin(
                plan_id=plan.id,
                date=today - timedelta(days=1),
                stage_index=0,
                feeling=Feeling.WORSE,
                tasks_done=[],
            )
        )
        assert await checkins.count_for_stage(plan.id, 0) == 2
        assert list(await checkins.last_feelings(plan.id, 2)) == [Feeling.WORSE, Feeling.WORSE]
        assert len(await checkins.recent_any(plan.id, 10)) == 2

        await plans.set_status(plan.id, PlanStatus.ESCALATED, datetime.now(UTC))
        await sessions.set_status(sess.id, SessionStatus.REFERRED, datetime.now(UTC))
        assert await plans.get_active_for_user(user.id) is None

        await llm_calls.add(
            task=LlmTask.CLASSIFY_COMPLAINT,
            model="test",
            session_id=sess.id,
            prompt_hash="abc",
            request={"user": "текст"},
            response={"scenario_id": "football.ankle_sprain"},
            valid=True,
            error=None,
            tokens_in=1,
            tokens_out=2,
            latency_ms=10,
        )
        await events.add(
            EventType.TRIAGE_COMPLETED,
            user_id=user.id,
            session_id=sess.id,
            payload={"outcome": "refer_specialist"},
        )
        await session.flush()

    async def test_duplicate_checkin_rejected(self, session: AsyncSession) -> None:
        from sqlalchemy.exc import IntegrityError

        users = SqlUserRepository(session)
        sessions = SqlSessionRepository(session)
        plans = SqlPlanRepository(session)
        checkins = SqlCheckinRepository(session)

        user = await users.create(tg_id=unique_tg_id() + 1, username="dup", locale="ru")
        sess = await sessions.create(user.id, Sport.BASKETBALL)
        plan = await plans.create(sess.id, "p", {"stages": []})

        day = date.today()
        await checkins.add(
            Checkin(plan_id=plan.id, date=day, stage_index=0, feeling=Feeling.BETTER)
        )
        with pytest.raises(IntegrityError):
            await checkins.add(
                Checkin(plan_id=plan.id, date=day, stage_index=0, feeling=Feeling.WORSE)
            )

    async def test_export_queries_run(self, session: AsyncSession) -> None:
        export = SqlExportRepository(session)
        assert isinstance(await export.sessions(), list)
        assert isinstance(await export.checkins(), list)
        assert isinstance(await export.funnel(), list)
