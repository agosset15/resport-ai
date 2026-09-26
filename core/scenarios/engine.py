"""Интерпретатор графа сценария.

Единственный источник истины по маршрутизации. Детерминирован: одни и те же ответы
всегда дают один и тот же исход. LLM сюда не заглядывает.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.domain.enums import Outcome
from core.domain.scenario import Question, RedFlag, Scenario

Answers = Mapping[str, str]


class ConditionError(ValueError):
    """Некорректное условие. На проде недостижимо: loader валидирует схему на старте."""


def evaluate_condition(
    condition: Mapping[str, object], answers: Answers, subject: str | None = None
) -> bool:
    """Вычисляет условие. Неотвеченный вопрос трактуется как «не совпало»."""
    if not condition:
        raise ConditionError("Пустое условие")

    for key, value in condition.items():
        if key == "all":
            return all(evaluate_condition(c, answers, subject) for c in _as_list(value))
        if key == "any":
            return any(evaluate_condition(c, answers, subject) for c in _as_list(value))
        if key == "not":
            return not evaluate_condition(_as_mapping(value), answers, subject)
        if key == "equals":
            return subject is not None and subject == value
        if key == "in":
            return subject is not None and subject in _as_list(value)
        # иначе key — это question_key
        actual = answers.get(key)
        if actual is None:
            return False
        expected = [value] if isinstance(value, str) else list(_as_list(value))
        return actual in expected

    raise ConditionError(f"Не удалось разобрать условие: {condition!r}")


def _as_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise ConditionError(f"Ожидался список, получено: {value!r}")
    return value


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ConditionError(f"Ожидался объект-условие, получено: {value!r}")
    return value


@dataclass(frozen=True, slots=True)
class TriageDecision:
    outcome: Outcome
    plan_key: str | None = None
    reason_codes: tuple[str, ...] = ()
    triggered_flags: tuple[str, ...] = ()

    @property
    def is_referral(self) -> bool:
        return self.outcome is Outcome.REFER_SPECIALIST


@dataclass(frozen=True, slots=True)
class AskQuestion:
    question: Question
    asked_count: int
    total_count: int


EngineStep = AskQuestion | TriageDecision


class ScenarioEngine:
    """Обёртка над одним сценарием. Состояния не хранит — всё приходит в `answers`."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    # --- вопросы -------------------------------------------------------------

    def applicable_questions(self, answers: Answers) -> tuple[Question, ...]:
        """Вопросы, релевантные текущим ответам (с учётом ask_if)."""
        return tuple(
            q
            for q in self.scenario.questions
            if q.ask_if is None or evaluate_condition(q.ask_if, answers)
        )

    def next_question(self, answers: Answers) -> Question | None:
        for question in self.applicable_questions(answers):
            if question.key not in answers:
                return question
        return None

    def progress(self, answers: Answers) -> tuple[int, int]:
        applicable = self.applicable_questions(answers)
        answered = sum(1 for q in applicable if q.key in answers)
        return answered, len(applicable)

    # --- red flags -----------------------------------------------------------

    def check_red_flags(self, answers: Answers) -> RedFlag | None:
        """Первый сработавший red flag. Проверяется после каждого ответа."""
        for flag in self.scenario.red_flags:
            answer = answers.get(flag.question)
            if answer is None:
                continue
            if evaluate_condition(flag.when, answers, subject=answer):
                return flag
        return None

    # --- маршрутизация -------------------------------------------------------

    def route(self, answers: Answers) -> TriageDecision:
        flag = self.check_red_flags(answers)
        if flag is not None:
            return TriageDecision(
                outcome=flag.outcome,
                reason_codes=(flag.id,),
                triggered_flags=(flag.id,),
            )

        for rule in self.scenario.routing:
            if rule.is_default or evaluate_condition(_as_mapping(rule.when), answers):
                reason = rule.reason_code or ("default" if rule.is_default else "routing_match")
                return TriageDecision(
                    outcome=rule.outcome,
                    plan_key=rule.plan,
                    reason_codes=(reason,),
                )

        # недостижимо: loader требует default-правило
        raise ConditionError(f"{self.scenario.id}: ни одно routing-правило не сработало")

    # --- единая точка входа для сервиса --------------------------------------

    def step(self, answers: Answers) -> EngineStep:
        """Что делать дальше: задать вопрос или выдать исход.

        Red flags проверяются до вопросов — сработавший флаг обрывает опрос.
        """
        flag = self.check_red_flags(answers)
        if flag is not None:
            return TriageDecision(
                outcome=flag.outcome,
                reason_codes=(flag.id,),
                triggered_flags=(flag.id,),
            )

        question = self.next_question(answers)
        if question is not None:
            answered, total = self.progress(answers)
            return AskQuestion(question=question, asked_count=answered + 1, total_count=total)

        return self.route(answers)

    def red_flag(self, flag_id: str) -> RedFlag | None:
        for flag in self.scenario.red_flags:
            if flag.id == flag_id:
                return flag
        return None
