"""Модель декларативного сценария. Только данные, без I/O и без парсинга YAML.

Грамматика условий (общая для red_flags / ask_if / routing):

    {"all": [cond, ...]}          — конъюнкция
    {"any": [cond, ...]}          — дизъюнкция
    {"not": cond}                 — отрицание
    {"equals": "opt"}             — сравнение с неявным субъектом (ответ на red_flag.question)
    {"in": ["a", "b"]}            — вхождение, неявный субъект
    {"<question_key>": "opt"}     — ответ на конкретный вопрос
    {"<question_key>": ["a","b"]} — ответ на вопрос входит в список

Ключи all/any/not/equals/in зарезервированы; любой другой ключ — key вопроса.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from core.domain.enums import Feeling, Outcome, Sport

RESERVED_CONDITION_KEYS = frozenset({"all", "any", "not", "equals", "in"})


@dataclass(frozen=True, slots=True)
class Option:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class Question:
    key: str
    text: str
    options: tuple[Option, ...]
    ask_if: Mapping[str, object] | None = None
    allow_free_text: bool = True
    hint: str | None = None

    def option_ids(self) -> tuple[str, ...]:
        return tuple(o.id for o in self.options)

    def option(self, option_id: str) -> Option | None:
        for o in self.options:
            if o.id == option_id:
                return o
        return None


@dataclass(frozen=True, slots=True)
class RedFlag:
    """Проверяется сразу после ответа на `question`; срабатывание обрывает опрос."""

    id: str
    question: str
    when: Mapping[str, object]
    outcome: Outcome
    reason: str


@dataclass(frozen=True, slots=True)
class RoutingRule:
    outcome: Outcome
    when: Mapping[str, object] | None = None  # None == default-правило
    plan: str | None = None
    reason_code: str | None = None

    @property
    def is_default(self) -> bool:
        return self.when is None


@dataclass(frozen=True, slots=True)
class CheckinCondition:
    """Условие над историей чек-инов этапа.

    feeling:      допустимые значения самочувствия
    consecutive:  сколько подряд идущих чек-инов должны подойти (по умолчанию 1)
    min_days:     минимальное число дней на этапе
    tasks_done_ratio_gte: минимальная доля выполненных задач в этих чек-инах
    """

    feeling: tuple[Feeling, ...] = ()
    consecutive: int = 1
    min_days: int | None = None
    tasks_done_ratio_gte: float | None = None

    @property
    def is_empty(self) -> bool:
        return not self.feeling and self.min_days is None and self.tasks_done_ratio_gte is None


@dataclass(frozen=True, slots=True)
class PlanTask:
    key: str
    text: str


@dataclass(frozen=True, slots=True)
class Stage:
    key: str
    title: str
    days: int
    tasks: tuple[PlanTask, ...]
    description: str | None = None
    advance_if: CheckinCondition = field(default_factory=CheckinCondition)
    escalate_if: CheckinCondition | None = None


@dataclass(frozen=True, slots=True)
class Plan:
    key: str
    title: str
    stages: tuple[Stage, ...]
    completion_text: str


@dataclass(frozen=True, slots=True)
class ScenarioTexts:
    """Статичные тексты-фоллбэки: используются, если LLM недоступна или дала невалидный ответ."""

    refer_specialist: str
    recovery_plan_intro: str
    escalation: str


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    version: int
    sport: Sport
    title: str
    entry_hints: tuple[str, ...]
    questions: tuple[Question, ...]
    red_flags: tuple[RedFlag, ...]
    routing: tuple[RoutingRule, ...]
    plans: Mapping[str, Plan]
    texts: ScenarioTexts
    summary: str | None = None

    def question(self, key: str) -> Question | None:
        for q in self.questions:
            if q.key == key:
                return q
        return None

    def question_keys(self) -> tuple[str, ...]:
        return tuple(q.key for q in self.questions)


@dataclass(frozen=True, slots=True)
class ScenarioRegistry:
    """Все загруженные сценарии. Строится один раз на старте процесса."""

    scenarios: Mapping[str, Scenario]

    def get(self, scenario_id: str) -> Scenario | None:
        return self.scenarios.get(scenario_id)

    def require(self, scenario_id: str) -> Scenario:
        scenario = self.scenarios.get(scenario_id)
        if scenario is None:
            raise KeyError(f"Сценарий не найден: {scenario_id}")
        return scenario

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.scenarios))

    def for_sport(self, sport: Sport) -> tuple[Scenario, ...]:
        return tuple(s for s in self.scenarios.values() if s.sport is sport)

    def sports(self) -> tuple[Sport, ...]:
        seen: list[Sport] = []
        for s in self.scenarios.values():
            if s.sport not in seen:
                seen.append(s.sport)
        return tuple(seen)


def all_option_ids(scenarios: Sequence[Scenario]) -> tuple[str, ...]:
    ids: list[str] = []
    for scenario in scenarios:
        for question in scenario.questions:
            for option in question.options:
                if option.id not in ids:
                    ids.append(option.id)
    return tuple(ids)
