"""Опрос и сортировка: от свободного описания до исхода.

Порядок фиксирован и не зависит от LLM:
    классификация (LLM, с фоллбэком на кнопки)
        -> детерминированный граф вопросов
        -> red flags
        -> routing
        -> исход (специалист | план восстановления)
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from core.config import LlmSettings
from core.domain.entities import Answer, Session, TriageResult, User
from core.domain.enums import AnswerSource, EventType, Outcome, SessionStatus, Sport
from core.domain.scenario import Question, Scenario, ScenarioRegistry
from core.llm.runner import LlmRunner
from core.llm.tasks.classify import classify_complaint
from core.llm.tasks.explain import explain_step, fallback_text
from core.llm.tasks.normalize import normalize_answer
from core.scenarios.engine import AskQuestion, ScenarioEngine, TriageDecision
from core.services.dto import (
    AnswerAccepted,
    ClassificationResult,
    OutcomeView,
    QuestionView,
    ScenarioChoice,
    TriageStep,
)
from core.services.protocols import (
    EventRepository,
    SessionRepository,
    TriageRepository,
)
from infra.telemetry import get_logger

log = get_logger("services.triage")


class TriageService:
    def __init__(
        self,
        sessions: SessionRepository,
        triage: TriageRepository,
        events: EventRepository,
        registry: ScenarioRegistry,
        llm: LlmRunner,
        llm_settings: LlmSettings,
    ) -> None:
        self._sessions = sessions
        self._triage = triage
        self._events = events
        self._registry = registry
        self._llm = llm
        self._llm_settings = llm_settings

    # --- начало ---------------------------------------------------------------

    async def start_session(self, user: User, sport: Sport) -> Session:
        await self._sessions.abandon_active(user.id)
        session = await self._sessions.create(user_id=user.id, sport=sport)
        await self._events.add(
            EventType.SPORT_SELECTED,
            user_id=user.id,
            session_id=session.id,
            payload={"sport": sport.value},
        )
        return session

    async def submit_complaint(self, session: Session, text: str) -> ClassificationResult:
        """Классифицирует жалобу. Не уверены — отдаём список кнопок."""
        session.complaint_text = text
        await self._sessions.update(session)
        await self._events.add(
            EventType.COMPLAINT_SUBMITTED,
            user_id=session.user_id,
            session_id=session.id,
            payload={"length": len(text)},
        )

        classification = await classify_complaint(
            self._llm,
            self._llm_settings,
            self._registry,
            complaint=text,
            sport=session.sport,
            session_id=session.id,
        )

        if classification is None:
            await self._events.add(
                EventType.SCENARIO_FALLBACK,
                user_id=session.user_id,
                session_id=session.id,
                payload={"reason": "low_confidence_or_unavailable"},
            )
            return ClassificationResult(
                session_id=session.id,
                scenario_id=None,
                confidence=None,
                choices=self.choices_for(session.sport),
            )

        await self.select_scenario(session, classification.scenario_id)
        await self._events.add(
            EventType.SCENARIO_CLASSIFIED,
            user_id=session.user_id,
            session_id=session.id,
            payload={
                "scenario_id": classification.scenario_id,
                "confidence": classification.confidence,
                "body_part": classification.body_part,
            },
        )
        return ClassificationResult(
            session_id=session.id,
            scenario_id=classification.scenario_id,
            confidence=classification.confidence,
        )

    def choices_for(self, sport: Sport) -> tuple[ScenarioChoice, ...]:
        return tuple(
            ScenarioChoice(scenario_id=s.id, title=s.title, sport=s.sport)
            for s in self._registry.for_sport(sport)
        )

    async def select_scenario(self, session: Session, scenario_id: str) -> Session:
        scenario = self._registry.require(scenario_id)
        session.scenario_id = scenario.id
        session.scenario_version = scenario.version
        await self._sessions.update(session)
        return session

    # --- опрос ----------------------------------------------------------------

    def engine_for(self, session: Session) -> ScenarioEngine:
        if session.scenario_id is None:
            raise ValueError("У сессии не выбран сценарий")
        return ScenarioEngine(self._registry.require(session.scenario_id))

    def scenario_of(self, session: Session) -> Scenario:
        return self.engine_for(session).scenario

    async def current_step(self, session: Session) -> TriageStep:
        engine = self.engine_for(session)
        answers = await self._sessions.answers_map(session.id)
        step = engine.step(answers)
        if isinstance(step, AskQuestion):
            return QuestionView(
                question=step.question, number=step.asked_count, total=step.total_count
            )
        return await self._finalize(session, engine, step, answers)

    async def answer_with_option(
        self, session: Session, question_key: str, option_id: str
    ) -> AnswerAccepted:
        engine = self.engine_for(session)
        question = engine.scenario.question(question_key)
        if question is None or question.option(option_id) is None:
            return AnswerAccepted(accepted=False)
        await self._store_answer(session, question, option_id, AnswerSource.BUTTON, None)
        return AnswerAccepted(accepted=True, option_id=option_id)

    async def answer_with_text(
        self, session: Session, question: Question, raw_text: str
    ) -> AnswerAccepted:
        """Свободный текст -> option_id через LLM. Не распозналось — переспрос кнопками."""
        option_id = await normalize_answer(self._llm, question, raw_text, session_id=session.id)
        if option_id is None:
            answers = await self._sessions.answers_map(session.id)
            answered, total = self.engine_for(session).progress(answers)
            return AnswerAccepted(
                accepted=False,
                repeat_question=QuestionView(question=question, number=answered + 1, total=total),
            )
        await self._store_answer(session, question, option_id, AnswerSource.LLM, raw_text)
        return AnswerAccepted(accepted=True, option_id=option_id)

    async def _store_answer(
        self,
        session: Session,
        question: Question,
        option_id: str,
        source: AnswerSource,
        raw_text: str | None,
    ) -> None:
        await self._sessions.upsert_answer(
            Answer(
                session_id=session.id,
                question_key=question.key,
                option_id=option_id,
                source=source,
                raw_text=raw_text,
            )
        )
        await self._events.add(
            EventType.QUESTION_ANSWERED,
            user_id=session.user_id,
            session_id=session.id,
            payload={
                "question_key": question.key,
                "option_id": option_id,
                "source": source.value,
            },
        )

    # --- исход ----------------------------------------------------------------

    async def _finalize(
        self,
        session: Session,
        engine: ScenarioEngine,
        decision: TriageDecision,
        answers: dict[str, str],
    ) -> OutcomeView:
        scenario = engine.scenario

        if decision.triggered_flags:
            await self._events.add(
                EventType.RED_FLAG_TRIGGERED,
                user_id=session.user_id,
                session_id=session.id,
                payload={"flags": list(decision.triggered_flags)},
            )

        explanation = await explain_step(
            self._llm, scenario, decision, answers, session_id=session.id
        )
        llm_explained = explanation is not None
        text = explanation or fallback_text(scenario, decision)

        await self._triage.upsert(
            TriageResult(
                session_id=session.id,
                outcome=decision.outcome,
                reason_codes=list(decision.reason_codes),
                triggered_flags=list(decision.triggered_flags),
                explanation_text=text,
            )
        )

        if decision.outcome is Outcome.REFER_SPECIALIST:
            session.status = SessionStatus.REFERRED
            session.finished_at = datetime.now(UTC)
            await self._sessions.update(session)

        await self._events.add(
            EventType.TRIAGE_COMPLETED,
            user_id=session.user_id,
            session_id=session.id,
            payload={
                "outcome": decision.outcome.value,
                "reason_codes": list(decision.reason_codes),
                "scenario_id": scenario.id,
                "llm_explained": llm_explained,
            },
        )
        log.info(
            "triage.completed",
            session_id=str(session.id),
            outcome=decision.outcome.value,
            scenario_id=scenario.id,
            flags=list(decision.triggered_flags),
        )

        return OutcomeView(
            outcome=decision.outcome,
            text=text,
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            reason_codes=decision.reason_codes,
            triggered_flags=decision.triggered_flags,
            plan_key=decision.plan_key,
            plan_title=(
                scenario.plans[decision.plan_key].title
                if decision.plan_key and decision.plan_key in scenario.plans
                else None
            ),
            llm_explained=llm_explained,
        )

    async def pending_decision(self, session: Session) -> TriageDecision | None:
        """Решение движка без побочных эффектов — нужно трекеру, чтобы создать план."""
        engine = self.engine_for(session)
        answers = await self._sessions.answers_map(session.id)
        step = engine.step(answers)
        return None if isinstance(step, AskQuestion) else step

    async def get_session(self, session_id: UUID) -> Session | None:
        return await self._sessions.get(session_id)

    async def active_session(self, user: User) -> Session | None:
        return await self._sessions.get_active(user.id)
