"""Исход self_rehab на уровне сервиса: гейт согласия и путь отказа.

Главное требование: самостоятельное восстановление не начинается без явного согласия
с предупреждением, а отказ закрывает сессию направлением к специалисту.
"""

from __future__ import annotations

import pytest

from core.config import LlmSettings
from core.domain.enums import EventType, Outcome, SessionStatus, Sport
from core.domain.scenario import ScenarioRegistry
from core.llm.runner import LlmRunner
from core.services.dto import OutcomeView
from core.services.triage import TriageService
from tests.fakes import (
    FakeEventRepository,
    FakeLlmCallRepository,
    FakeSessionRepository,
    FakeTriageRepository,
    FakeUserRepository,
    ScriptedLlmProvider,
)

SCENARIO_ID = "football.bruise"


class Harness:
    def __init__(self, registry: ScenarioRegistry) -> None:
        self.users = FakeUserRepository()
        self.sessions = FakeSessionRepository()
        self.triage_repo = FakeTriageRepository()
        self.events = FakeEventRepository()
        self.audit = FakeLlmCallRepository()
        self.settings = LlmSettings(provider="scripted", api_key="x")
        self.runner = LlmRunner(ScriptedLlmProvider(fail=True), self.settings, self.audit)
        self.service = TriageService(
            sessions=self.sessions,
            triage=self.triage_repo,
            events=self.events,
            registry=registry,
            llm=self.runner,
            llm_settings=self.settings,
        )

    async def session_with(self, **answers: str):
        user = await self.users.create(tg_id=1, username="test", locale="ru")
        session = await self.service.start_session(user, Sport.FOOTBALL)
        await self.service.select_scenario(session, SCENARIO_ID)
        for question_key, option_id in answers.items():
            await self.service.answer_with_option(session, question_key, option_id)
        return user, session

    def event_types(self) -> list[EventType]:
        return self.events.types()


@pytest.fixture
def harness(registry: ScenarioRegistry) -> Harness:
    return Harness(registry)


class TestOutcome:
    async def test_default_rule_yields_self_rehab_with_a_plan(self, harness: Harness) -> None:
        _, session = await harness.session_with(q_deformity="absent", q_swelling="shrinking")
        step = await harness.service.current_step(session)

        assert isinstance(step, OutcomeView)
        assert step.outcome is Outcome.SELF_REHAB
        assert step.plan_key == "bruise_basic"
        assert step.reason_codes == ("default_self_rehab",)

    async def test_watch_rule_yields_the_guarded_plan(self, harness: Harness) -> None:
        _, session = await harness.session_with(q_deformity="absent", q_swelling="stable")
        step = await harness.service.current_step(session)

        assert isinstance(step, OutcomeView)
        assert step.outcome is Outcome.SELF_REHAB
        assert step.plan_key == "bruise_guarded"

    async def test_fallback_text_uses_self_rehab_preamble(self, harness: Harness) -> None:
        """LLM недоступна — текст берётся из texts.self_rehab_intro, а не из плана."""
        _, session = await harness.session_with(q_deformity="absent", q_swelling="shrinking")
        step = await harness.service.current_step(session)

        assert isinstance(step, OutcomeView)
        assert "Гарантий я не даю" in step.text
        assert step.llm_explained is False

    async def test_danger_sign_still_refers(self, harness: Harness) -> None:
        _, session = await harness.session_with(q_deformity="present")
        step = await harness.service.current_step(session)

        assert isinstance(step, OutcomeView)
        assert step.outcome is Outcome.REFER_SPECIALIST
        assert step.triggered_flags == ("rf_deformity",)

    async def test_offer_is_recorded_as_an_event(self, harness: Harness) -> None:
        _, session = await harness.session_with(q_deformity="absent", q_swelling="shrinking")
        await harness.service.current_step(session)
        assert EventType.SELF_REHAB_OFFERED in harness.event_types()


class TestConsentGate:
    async def test_session_stays_open_until_the_user_agrees(self, harness: Harness) -> None:
        """Исход self_rehab не закрывает сессию: впереди согласие и выдача плана."""
        _, session = await harness.session_with(q_deformity="absent", q_swelling="shrinking")
        await harness.service.current_step(session)

        stored = await harness.service.get_session(session.id)
        assert stored is not None
        assert stored.status is SessionStatus.IN_PROGRESS

    async def test_confirmation_is_recorded(self, harness: Harness) -> None:
        _, session = await harness.session_with(q_deformity="absent", q_swelling="shrinking")
        await harness.service.current_step(session)
        await harness.service.confirm_self_rehab(session)
        assert EventType.SELF_REHAB_STARTED in harness.event_types()

    async def test_decline_closes_session_with_a_referral(self, harness: Harness) -> None:
        _, session = await harness.session_with(q_deformity="absent", q_swelling="shrinking")
        await harness.service.current_step(session)

        text = await harness.service.request_specialist(
            session,
            reason_code="user_declined_self_rehab",
            event=EventType.SELF_REHAB_DECLINED,
        )

        assert "очный осмотр" in text
        stored_result = harness.triage_repo.results[session.id]
        assert stored_result.outcome is Outcome.REFER_SPECIALIST
        assert stored_result.reason_codes == ["user_declined_self_rehab"]

        stored = await harness.service.get_session(session.id)
        assert stored is not None
        assert stored.status is SessionStatus.REFERRED
        assert stored.finished_at is not None
        assert EventType.SELF_REHAB_DECLINED in harness.event_types()


class TestPainPoint:
    async def test_confirmation_and_rejection_are_recorded(self, harness: Harness) -> None:
        _, session = await harness.session_with()
        await harness.service.note_pain_point(session, confirmed=True)
        await harness.service.note_pain_point(session, confirmed=False)

        types = harness.event_types()
        assert EventType.PAIN_POINT_CONFIRMED in types
        assert EventType.PAIN_POINT_REJECTED in types

    async def test_doctor_button_closes_session(self, harness: Harness) -> None:
        """Кнопка «Запись к врачу» на карте боли уводит к специалисту без опроса."""
        _, session = await harness.session_with()
        await harness.service.request_specialist(
            session,
            reason_code="user_requested_doctor",
            event=EventType.SPECIALIST_REQUESTED,
        )

        stored = await harness.service.get_session(session.id)
        assert stored is not None
        assert stored.status is SessionStatus.REFERRED
        assert EventType.SPECIALIST_REQUESTED in harness.event_types()
