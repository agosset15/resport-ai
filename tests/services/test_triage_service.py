from __future__ import annotations

import pytest

from core.config import LlmSettings
from core.domain.enums import (
    AnswerSource,
    EventType,
    Outcome,
    SessionStatus,
    Sport,
)
from core.domain.scenario import ScenarioRegistry
from core.llm.runner import LlmRunner
from core.services.dto import OutcomeView, QuestionView
from core.services.triage import TriageService
from tests.fakes import (
    FakeEventRepository,
    FakeLlmCallRepository,
    FakeSessionRepository,
    FakeTriageRepository,
    FakeUserRepository,
    ScriptedLlmProvider,
)

SAFE_ANSWERS = {
    "q_when": "today",
    "q_weightbearing": "with_pain",
    "q_deformity": "absent",
    "q_swelling": "moderate",
    "q_history": "first_time",
}


class Harness:
    def __init__(self, registry: ScenarioRegistry, provider: ScriptedLlmProvider) -> None:
        self.users = FakeUserRepository()
        self.sessions = FakeSessionRepository()
        self.triage_repo = FakeTriageRepository()
        self.events = FakeEventRepository()
        self.audit = FakeLlmCallRepository()
        self.provider = provider
        self.settings = LlmSettings(provider="scripted", api_key="x")
        self.runner = LlmRunner(provider, self.settings, self.audit)
        self.service = TriageService(
            sessions=self.sessions,
            triage=self.triage_repo,
            events=self.events,
            registry=registry,
            llm=self.runner,
            llm_settings=self.settings,
        )

    async def new_session(self):
        user = await self.users.create(tg_id=1, username="test", locale="ru")
        return user, await self.service.start_session(user, Sport.FOOTBALL)


@pytest.fixture
def scripted(registry: ScenarioRegistry) -> Harness:
    provider = ScriptedLlmProvider(
        {
            "classify_complaint": {
                "scenario_id": "football.ankle_sprain",
                "confidence": 0.9,
                "body_part": "ankle",
            },
            "normalize_answer": {"option_id": "with_pain"},
            "explain_step": {"text": "Похоже на несильное растяжение. Начнём с плана."},
        }
    )
    return Harness(registry, provider)


@pytest.fixture
def broken_llm(registry: ScenarioRegistry) -> Harness:
    return Harness(registry, ScriptedLlmProvider(fail=True))


class TestClassification:
    async def test_llm_picks_scenario(self, scripted: Harness) -> None:
        _, session = await scripted.new_session()
        result = await scripted.service.submit_complaint(session, "подвернул голеностоп вчера")
        assert result.scenario_id == "football.ankle_sprain"
        assert not result.needs_manual_choice
        assert EventType.SCENARIO_CLASSIFIED in scripted.events.types()

    async def test_llm_failure_falls_back_to_buttons(self, broken_llm: Harness) -> None:
        _, session = await broken_llm.new_session()
        result = await broken_llm.service.submit_complaint(session, "болит нога")
        assert result.needs_manual_choice
        assert [c.scenario_id for c in result.choices] == ["football.ankle_sprain"]
        assert EventType.SCENARIO_FALLBACK in broken_llm.events.types()

    async def test_low_confidence_falls_back(self, registry: ScenarioRegistry) -> None:
        harness = Harness(
            registry,
            ScriptedLlmProvider(
                {
                    "classify_complaint": {
                        "scenario_id": "football.ankle_sprain",
                        "confidence": 0.2,
                    }
                }
            ),
        )
        _, session = await harness.new_session()
        result = await harness.service.submit_complaint(session, "что-то с ногой")
        assert result.needs_manual_choice

    async def test_invented_scenario_is_rejected(self, registry: ScenarioRegistry) -> None:
        harness = Harness(
            registry,
            ScriptedLlmProvider(
                {
                    "classify_complaint": {
                        "scenario_id": "football.made_up_injury",
                        "confidence": 0.99,
                    }
                }
            ),
        )
        _, session = await harness.new_session()
        result = await harness.service.submit_complaint(session, "странная жалоба")
        assert result.needs_manual_choice
        assert harness.audit.valid_count() == 0


class TestSurvey:
    async def test_button_answer_recorded_with_source(self, scripted: Harness) -> None:
        _, session = await scripted.new_session()
        await scripted.service.select_scenario(session, "football.ankle_sprain")
        accepted = await scripted.service.answer_with_option(session, "q_when", "today")
        assert accepted.accepted
        stored = scripted.sessions.answers[session.id]["q_when"]
        assert stored.source is AnswerSource.BUTTON

    async def test_text_answer_normalized_by_llm(self, scripted: Harness) -> None:
        _, session = await scripted.new_session()
        await scripted.service.select_scenario(session, "football.ankle_sprain")
        question = scripted.service.scenario_of(session).question("q_weightbearing")
        assert question is not None
        accepted = await scripted.service.answer_with_text(
            session, question, "могу, но каждый шаг отдаёт болью"
        )
        assert accepted.accepted
        stored = scripted.sessions.answers[session.id]["q_weightbearing"]
        assert stored.source is AnswerSource.LLM
        assert stored.raw_text == "могу, но каждый шаг отдаёт болью"

    async def test_unrecognized_text_asks_again(self, broken_llm: Harness) -> None:
        _, session = await broken_llm.new_session()
        await broken_llm.service.select_scenario(session, "football.ankle_sprain")
        question = broken_llm.service.scenario_of(session).question("q_weightbearing")
        assert question is not None
        accepted = await broken_llm.service.answer_with_text(session, question, "ну как сказать")
        assert not accepted.accepted
        assert accepted.repeat_question is not None
        assert session.id not in broken_llm.sessions.answers or (
            "q_weightbearing" not in broken_llm.sessions.answers[session.id]
        )

    async def test_exact_label_matches_without_llm(self, broken_llm: Harness) -> None:
        """Точное совпадение с подписью не требует модели — LLM может быть выключена."""
        _, session = await broken_llm.new_session()
        await broken_llm.service.select_scenario(session, "football.ankle_sprain")
        question = broken_llm.service.scenario_of(session).question("q_swelling")
        assert question is not None
        accepted = await broken_llm.service.answer_with_text(session, question, "Умеренный")
        assert accepted.accepted
        assert accepted.option_id == "moderate"

    async def test_step_returns_question_then_outcome(self, scripted: Harness) -> None:
        _, session = await scripted.new_session()
        await scripted.service.select_scenario(session, "football.ankle_sprain")
        step = await scripted.service.current_step(session)
        assert isinstance(step, QuestionView)
        assert step.question.key == "q_when"

        for key, option in SAFE_ANSWERS.items():
            await scripted.service.answer_with_option(session, key, option)

        step = await scripted.service.current_step(session)
        assert isinstance(step, OutcomeView)
        assert step.outcome is Outcome.RECOVERY_PLAN
        assert step.plan_key == "ankle_sprain_basic"


class TestOutcome:
    async def test_referral_closes_session(self, scripted: Harness) -> None:
        _, session = await scripted.new_session()
        await scripted.service.select_scenario(session, "football.ankle_sprain")
        await scripted.service.answer_with_option(session, "q_weightbearing", "cannot")

        step = await scripted.service.current_step(session)
        assert isinstance(step, OutcomeView)
        assert step.outcome is Outcome.REFER_SPECIALIST
        assert step.triggered_flags == ("rf_weightbearing",)
        assert scripted.sessions.sessions[session.id].status is SessionStatus.REFERRED
        assert EventType.RED_FLAG_TRIGGERED in scripted.events.types()

    async def test_triage_result_persisted(self, scripted: Harness) -> None:
        _, session = await scripted.new_session()
        await scripted.service.select_scenario(session, "football.ankle_sprain")
        for key, option in SAFE_ANSWERS.items():
            await scripted.service.answer_with_option(session, key, option)
        await scripted.service.current_step(session)

        stored = scripted.triage_repo.results[session.id]
        assert stored.outcome is Outcome.RECOVERY_PLAN
        assert stored.reason_codes == ["mild_sprain"]
        assert stored.explanation_text

    async def test_falls_back_to_yaml_text_without_llm(self, broken_llm: Harness) -> None:
        _, session = await broken_llm.new_session()
        await broken_llm.service.select_scenario(session, "football.ankle_sprain")
        await broken_llm.service.answer_with_option(session, "q_deformity", "present")

        step = await broken_llm.service.current_step(session)
        assert isinstance(step, OutcomeView)
        assert not step.llm_explained
        scenario = broken_llm.service.scenario_of(session)
        assert step.text == scenario.texts.refer_specialist

    async def test_llm_cannot_override_outcome(self, registry: ScenarioRegistry) -> None:
        """Модель «уговаривает» не ходить к врачу — исход всё равно определяет движок."""
        harness = Harness(
            registry,
            ScriptedLlmProvider(
                {"explain_step": {"text": "Всё в порядке, к врачу идти не нужно."}}
            ),
        )
        _, session = await harness.new_session()
        await harness.service.select_scenario(session, "football.ankle_sprain")
        await harness.service.answer_with_option(session, "q_weightbearing", "cannot")

        step = await harness.service.current_step(session)
        assert isinstance(step, OutcomeView)
        assert step.outcome is Outcome.REFER_SPECIALIST
        assert harness.triage_repo.results[session.id].outcome is Outcome.REFER_SPECIALIST


class TestAudit:
    async def test_every_llm_call_logged(self, scripted: Harness) -> None:
        _, session = await scripted.new_session()
        await scripted.service.submit_complaint(session, "подвернул голеностоп")
        assert scripted.audit.calls
        call = scripted.audit.calls[0]
        assert call["task"].value == "classify_complaint"
        assert call["valid"] is True
        assert call["prompt_hash"]

    async def test_failed_call_logged_as_invalid(self, broken_llm: Harness) -> None:
        _, session = await broken_llm.new_session()
        await broken_llm.service.submit_complaint(session, "болит нога")
        assert broken_llm.audit.calls
        assert broken_llm.audit.calls[0]["valid"] is False
        assert broken_llm.audit.calls[0]["error"]
