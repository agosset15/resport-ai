"""DTO между сервисами и транспортом (бот сейчас, Mini App потом)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from core.domain.enums import Feeling, Outcome, Sport
from core.domain.scenario import Option, PlanTask, Question
from core.scenarios.plan_engine import TrackerAction


@dataclass(frozen=True, slots=True)
class ScenarioChoice:
    scenario_id: str
    title: str
    sport: Sport


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Что делать после свободного описания проблемы."""

    session_id: UUID
    scenario_id: str | None
    confidence: float | None
    choices: tuple[ScenarioChoice, ...] = ()

    @property
    def needs_manual_choice(self) -> bool:
        return self.scenario_id is None


@dataclass(frozen=True, slots=True)
class QuestionView:
    question: Question
    number: int
    total: int

    @property
    def options(self) -> tuple[Option, ...]:
        return self.question.options


@dataclass(frozen=True, slots=True)
class OutcomeView:
    outcome: Outcome
    text: str
    scenario_id: str
    scenario_title: str
    reason_codes: tuple[str, ...] = ()
    triggered_flags: tuple[str, ...] = ()
    plan_id: UUID | None = None
    plan_key: str | None = None
    plan_title: str | None = None
    llm_explained: bool = False


TriageStep = QuestionView | OutcomeView


@dataclass(frozen=True, slots=True)
class AnswerAccepted:
    """Результат попытки записать ответ пользователя."""

    accepted: bool
    option_id: str | None = None
    repeat_question: QuestionView | None = None


@dataclass(frozen=True, slots=True)
class StageView:
    plan_id: UUID
    plan_title: str
    stage_index: int
    stage_total: int
    stage_key: str
    stage_title: str
    stage_description: str | None
    day_number: int
    day_total: int
    tasks: tuple[PlanTask, ...]
    done_today: tuple[str, ...] = ()
    checkin_done_today: bool = False


@dataclass(frozen=True, slots=True)
class CheckinResult:
    action: TrackerAction
    text: str
    stage: StageView | None = None
    completed: bool = False
    escalated: bool = False


@dataclass(frozen=True, slots=True)
class PlanProgress:
    plan_id: UUID
    plan_title: str
    stage_index: int
    stage_total: int
    checkins: tuple[tuple[date, Feeling], ...] = field(default_factory=tuple)
