"""Сквозной путь пользователя без транспорта: жалоба → опрос → исход → трекер.

Повторяет 02_user_flow.puml на уровне сервисов.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.config import LlmSettings
from core.domain.enums import (
    EventType,
    Feeling,
    Outcome,
    PlanStatus,
    SessionStatus,
    Sport,
)
from core.domain.scenario import ScenarioRegistry
from core.llm.runner import LlmRunner
from core.scenarios.plan_engine import TrackerAction
from core.services.dto import OutcomeView, QuestionView
from core.services.tracker import TrackerService
from core.services.triage import TriageService
from core.services.user import UserService
from tests.fakes import (
    FakeCheckinRepository,
    FakeEventRepository,
    FakeLlmCallRepository,
    FakePlanRepository,
    FakeSessionRepository,
    FakeTriageRepository,
    FakeUserRepository,
    ScriptedLlmProvider,
)

START = date(2026, 5, 4)

ANSWERS_TO_PLAN = {
    "q_when": "today",
    "q_weightbearing": "with_pain",
    "q_deformity": "absent",
    "q_swelling": "moderate",
    "q_history": "first_time",
}


class App:
    """Минимальная сборка сервисов — то же, что собирает Dishka в проде."""

    def __init__(self, registry: ScenarioRegistry, provider: ScriptedLlmProvider) -> None:
        from core.config import ContentSettings

        self.users_repo = FakeUserRepository()
        self.sessions_repo = FakeSessionRepository()
        self.plans_repo = FakePlanRepository(self.sessions_repo)
        self.checkins_repo = FakeCheckinRepository()
        self.triage_repo = FakeTriageRepository()
        self.events = FakeEventRepository()
        self.audit = FakeLlmCallRepository()

        content = ContentSettings()
        llm_settings = LlmSettings(provider="scripted", api_key="x")
        runner = LlmRunner(provider, llm_settings, self.audit)

        self.users = UserService(self.users_repo, self.events, content)
        self.triage = TriageService(
            sessions=self.sessions_repo,
            triage=self.triage_repo,
            events=self.events,
            registry=registry,
            llm=runner,
            llm_settings=llm_settings,
        )
        self.tracker = TrackerService(
            plans=self.plans_repo,
            checkins=self.checkins_repo,
            sessions=self.sessions_repo,
            triage=self.triage_repo,
            events=self.events,
        )


@pytest.fixture
def app(registry: ScenarioRegistry) -> App:
    provider = ScriptedLlmProvider(
        {
            "classify_complaint": {
                "scenario_id": "football.ankle_sprain",
                "confidence": 0.92,
                "body_part": "ankle",
            },
            "normalize_answer": {"option_id": "with_pain"},
            "explain_step": {"text": "Похоже на растяжение. Начнём с плана восстановления."},
        }
    )
    return App(registry, provider)


async def onboard(app: App, tg_id: int = 42):
    user = await app.users.get_or_create(tg_id=tg_id, username="athlete")
    assert app.users.needs_consent(user)
    user = await app.users.accept_consent(user)
    assert not app.users.needs_consent(user)
    return user


class TestFullPath:
    async def test_complaint_to_completed_plan(self, app: App) -> None:
        user = await onboard(app)
        session = await app.triage.start_session(user, Sport.FOOTBALL)

        classification = await app.triage.submit_complaint(
            session, "вчера подвернул голеностоп на игре, опухло и больно наступать"
        )
        assert classification.scenario_id == "football.ankle_sprain"

        session = await app.triage.get_session(session.id)
        assert session is not None

        for _ in range(10):
            step = await app.triage.current_step(session)
            if isinstance(step, OutcomeView):
                break
            assert isinstance(step, QuestionView)
            await app.triage.answer_with_option(
                session, step.question.key, ANSWERS_TO_PLAN[step.question.key]
            )
        assert isinstance(step, OutcomeView)
        assert step.outcome is Outcome.RECOVERY_PLAN
        assert step.plan_key == "ankle_sprain_basic"
        assert step.llm_explained

        scenario = app.triage.scenario_of(session)
        plan, view = await app.tracker.start_plan(session, scenario, step.plan_key)
        assert view.stage_index == 0
        assert app.sessions_repo.sessions[session.id].status is SessionStatus.PLAN_ACTIVE

        day = START
        guard = 0
        while app.plans_repo.plans[plan.id].status is PlanStatus.ACTIVE and guard < 20:
            current = app.plans_repo.plans[plan.id]
            stage = app.tracker.plan_of(current).stages[current.current_stage]
            result = await app.tracker.submit_checkin(
                current,
                feeling=Feeling.BETTER,
                tasks_done=[t.key for t in stage.tasks],
                day=day,
            )
            day += timedelta(days=1)
            guard += 1
            if result.action is TrackerAction.COMPLETE:
                break

        assert app.plans_repo.plans[plan.id].status is PlanStatus.COMPLETED
        assert app.sessions_repo.sessions[session.id].status is SessionStatus.COMPLETED

        types = app.events.types()
        for expected in (
            EventType.BOT_STARTED,
            EventType.CONSENT_GIVEN,
            EventType.SPORT_SELECTED,
            EventType.COMPLAINT_SUBMITTED,
            EventType.SCENARIO_CLASSIFIED,
            EventType.QUESTION_ANSWERED,
            EventType.TRIAGE_COMPLETED,
            EventType.PLAN_STARTED,
            EventType.CHECKIN_SUBMITTED,
            EventType.STAGE_ADVANCED,
            EventType.PLAN_COMPLETED,
        ):
            assert expected in types, f"нет события {expected}"

    async def test_red_flag_path_never_reaches_tracker(self, app: App) -> None:
        user = await onboard(app, tg_id=43)
        session = await app.triage.start_session(user, Sport.FOOTBALL)
        await app.triage.submit_complaint(session, "подвернул голеностоп, не могу встать")

        session = await app.triage.get_session(session.id)
        assert session is not None
        await app.triage.answer_with_option(session, "q_when", "today")
        await app.triage.answer_with_option(session, "q_weightbearing", "cannot")

        step = await app.triage.current_step(session)
        assert isinstance(step, OutcomeView)
        assert step.outcome is Outcome.REFER_SPECIALIST
        assert step.plan_key is None
        assert app.sessions_repo.sessions[session.id].status is SessionStatus.REFERRED
        assert not app.plans_repo.plans

    async def test_tracker_escalation_returns_user_to_specialist(self, app: App) -> None:
        user = await onboard(app, tg_id=44)
        session = await app.triage.start_session(user, Sport.FOOTBALL)
        await app.triage.select_scenario(session, "football.ankle_sprain")
        for key, option in ANSWERS_TO_PLAN.items():
            await app.triage.answer_with_option(session, key, option)
        step = await app.triage.current_step(session)
        assert isinstance(step, OutcomeView)

        scenario = app.triage.scenario_of(session)
        plan, _ = await app.tracker.start_plan(session, scenario, "ankle_sprain_basic")

        await app.tracker.submit_checkin(plan, feeling=Feeling.WORSE, tasks_done=[], day=START)
        result = await app.tracker.submit_checkin(
            plan, feeling=Feeling.WORSE, tasks_done=[], day=START + timedelta(days=1)
        )

        assert result.escalated
        assert app.plans_repo.plans[plan.id].status is PlanStatus.ESCALATED
        assert app.triage_repo.results[session.id].outcome is Outcome.REFER_SPECIALIST
        assert app.sessions_repo.sessions[session.id].status is SessionStatus.REFERRED

    async def test_new_session_abandons_previous(self, app: App) -> None:
        user = await onboard(app, tg_id=45)
        first = await app.triage.start_session(user, Sport.FOOTBALL)
        second = await app.triage.start_session(user, Sport.BASKETBALL)

        assert app.sessions_repo.sessions[first.id].status is SessionStatus.ABANDONED
        assert app.sessions_repo.sessions[second.id].status is SessionStatus.IN_PROGRESS
        assert (await app.triage.active_session(user)).id == second.id  # type: ignore[union-attr]
