"""DTO между сервисами и транспортом (бот сейчас, Mini App потом)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from core.domain.enums import (
    DailyCapacity,
    Feeling,
    ItemKind,
    ItemStatus,
    Outcome,
    PlanSource,
    Sport,
    Swelling,
)
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
    suggested_region: str | None = None

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
class DailyItem:
    """Пункт плана на сегодня: упражнение или задача.

    Карточка упражнения — ровно то, что требует ТЗ: название, инструкция, подсказка
    посмотреть в интернете, дозировка, ограничения, отметка и комментарий.
    """

    kind: ItemKind
    key: str
    title: str
    instruction: str | None = None
    lookup_hint: str | None = None
    dosage: str | None = None
    limits: tuple[str, ...] = ()
    status: ItemStatus | None = None
    comment: str | None = None

    @property
    def is_marked(self) -> bool:
        return self.status is not None


@dataclass(frozen=True, slots=True)
class DailyPlanView:
    plan_id: UUID
    plan_title: str
    date: date
    stage_index: int
    stage_total: int
    stage_title: str
    stage_description: str | None
    day_number: int
    day_total: int
    items: tuple[DailyItem, ...]
    source: PlanSource = PlanSource.SCENARIO
    wellbeing_done: bool = False

    @property
    def done(self) -> int:
        return sum(1 for i in self.items if i.status is ItemStatus.DONE)

    @property
    def partial(self) -> int:
        return sum(1 for i in self.items if i.status is ItemStatus.PARTIAL)

    @property
    def skipped(self) -> int:
        return sum(1 for i in self.items if i.status is ItemStatus.SKIPPED)

    @property
    def all_marked(self) -> bool:
        return bool(self.items) and all(i.is_marked for i in self.items)

    def item(self, kind: ItemKind, key: str) -> DailyItem | None:
        return next((i for i in self.items if i.kind is kind and i.key == key), None)


@dataclass(frozen=True, slots=True)
class WellbeingView:
    """Одни и те же вопросы каждый день — иначе динамику не сравнить."""

    pain_0_10: int
    swelling: Swelling
    daily_capacity: DailyCapacity
    note: str | None = None


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
