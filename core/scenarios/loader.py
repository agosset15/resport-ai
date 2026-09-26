"""Загрузка и валидация YAML-сценариев.

Вызывается один раз на старте процесса. Любая ошибка в сценарии — исключение на старте,
а не сюрприз в середине опроса пользователя.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from core.domain.enums import Feeling, Outcome, Sport
from core.domain.scenario import (
    RESERVED_CONDITION_KEYS,
    CheckinCondition,
    Option,
    Plan,
    PlanTask,
    Question,
    RedFlag,
    RoutingRule,
    Scenario,
    ScenarioRegistry,
    ScenarioTexts,
    Stage,
)

SCHEMA_PATH = Path(__file__).with_name("schema.json")


class ScenarioValidationError(Exception):
    """Сценарий не прошёл валидацию. Сообщение содержит все найденные проблемы."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        super().__init__("Ошибки в сценариях:\n" + "\n".join(f"  - {e}" for e in self.errors))


def _load_schema() -> Draft202012Validator:
    with SCHEMA_PATH.open(encoding="utf-8") as fh:
        return Draft202012Validator(json.load(fh))


def _as_option(raw: Any, labels: Mapping[str, str]) -> Option:
    if isinstance(raw, str):
        return Option(id=raw, label=labels.get(raw, raw.replace("_", " ")))
    return Option(id=raw["id"], label=raw["label"])


def _as_checkin_condition(raw: Mapping[str, Any] | None) -> CheckinCondition | None:
    if raw is None:
        return None
    feeling_raw = raw.get("feeling")
    if feeling_raw is None:
        feelings: tuple[Feeling, ...] = ()
    elif isinstance(feeling_raw, str):
        feelings = (Feeling(feeling_raw),)
    else:
        feelings = tuple(Feeling(f) for f in feeling_raw)
    return CheckinCondition(
        feeling=feelings,
        consecutive=int(raw.get("consecutive", 1)),
        min_days=raw.get("min_days"),
        tasks_done_ratio_gte=raw.get("tasks_done_ratio_gte"),
    )


def _as_plan(key: str, raw: Mapping[str, Any]) -> Plan:
    stages = tuple(
        Stage(
            key=s["key"],
            title=s["title"],
            days=int(s["days"]),
            description=s.get("description"),
            tasks=tuple(PlanTask(key=t["key"], text=t["text"]) for t in s["tasks"]),
            advance_if=_as_checkin_condition(s["advance_if"]) or CheckinCondition(),
            escalate_if=_as_checkin_condition(s.get("escalate_if")),
        )
        for s in raw["stages"]
    )
    return Plan(
        key=key,
        title=raw["title"],
        stages=stages,
        completion_text=raw["completion_text"],
    )


def _build_scenario(raw: Mapping[str, Any]) -> Scenario:
    labels: Mapping[str, str] = raw.get("labels", {})
    questions = tuple(
        Question(
            key=q["key"],
            text=q["text"],
            options=tuple(_as_option(o, labels) for o in q["options"]),
            ask_if=q.get("ask_if"),
            allow_free_text=q.get("allow_free_text", True),
            hint=q.get("hint"),
        )
        for q in raw["questions"]
    )
    red_flags = tuple(
        RedFlag(
            id=rf["id"],
            question=rf["question"],
            when=rf["when"],
            outcome=Outcome(rf["outcome"]),
            reason=rf["reason"],
        )
        for rf in raw.get("red_flags", [])
    )
    routing = tuple(
        RoutingRule(
            outcome=Outcome(rule["outcome"]),
            when=rule.get("when") if "default" not in rule else None,
            plan=rule.get("plan"),
            reason_code=rule.get("reason_code"),
        )
        for rule in raw["routing"]
    )
    plans = {key: _as_plan(key, value) for key, value in raw.get("plans", {}).items()}
    texts_raw = raw["texts"]
    return Scenario(
        id=raw["id"],
        version=int(raw["version"]),
        sport=Sport(raw["sport"]),
        title=raw["title"],
        summary=raw.get("summary"),
        entry_hints=tuple(raw.get("entry_hints", [])),
        questions=questions,
        red_flags=red_flags,
        routing=routing,
        plans=plans,
        texts=ScenarioTexts(
            refer_specialist=texts_raw["refer_specialist"],
            recovery_plan_intro=texts_raw["recovery_plan_intro"],
            escalation=texts_raw["escalation"],
        ),
    )


def _as_sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, list | tuple) else [value]


def _condition_question_refs(condition: Mapping[str, Any]) -> Iterable[tuple[str, list[str]]]:
    """Достаёт из условия пары (question_key, допустимые option_id)."""
    for key, value in condition.items():
        if key in ("all", "any"):
            for sub in value:
                yield from _condition_question_refs(sub)
        elif key == "not":
            yield from _condition_question_refs(value)
        elif key in RESERVED_CONDITION_KEYS:
            continue
        else:
            options = [value] if isinstance(value, str) else list(value)
            yield key, options


def _validate_semantics(scenario: Scenario, raw: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    sid = scenario.id

    if not sid.startswith(f"{scenario.sport.value}."):
        errors.append(f"{sid}: id должен начинаться с '{scenario.sport.value}.'")

    keys = [q.key for q in scenario.questions]
    duplicates = {k for k in keys if keys.count(k) > 1}
    if duplicates:
        errors.append(f"{sid}: дублирующиеся question.key: {sorted(duplicates)}")

    position = {key: idx for idx, key in enumerate(keys)}

    def check_condition(
        condition: Mapping[str, Any], where: str, max_position: int | None = None
    ) -> None:
        for question_key, options in _condition_question_refs(condition):
            target = scenario.question(question_key)
            if target is None:
                errors.append(
                    f"{sid}/{where}: условие ссылается на неизвестный вопрос '{question_key}'"
                )
                continue
            if max_position is not None and position[question_key] >= max_position:
                errors.append(
                    f"{sid}/{where}: условие ссылается на вопрос '{question_key}', "
                    "который задаётся позже"
                )
            unknown = [o for o in options if o not in target.option_ids()]
            if unknown:
                errors.append(f"{sid}/{where}: у вопроса '{question_key}' нет опций {unknown}")

    for idx, question in enumerate(scenario.questions):
        option_ids = [o.id for o in question.options]
        if len(set(option_ids)) != len(option_ids):
            errors.append(f"{sid}/{question.key}: дублирующиеся option.id")
        if question.ask_if:
            check_condition(question.ask_if, f"{question.key}.ask_if", max_position=idx)

    flag_ids = [rf.id for rf in scenario.red_flags]
    if len(set(flag_ids)) != len(flag_ids):
        errors.append(f"{sid}: дублирующиеся red_flag.id")

    for flag in scenario.red_flags:
        flag_question = scenario.question(flag.question)
        if flag_question is None:
            errors.append(
                f"{sid}/{flag.id}: red_flag ссылается на неизвестный вопрос '{flag.question}'"
            )
            continue
        implicit = flag.when.get("equals") or flag.when.get("in")
        if implicit is not None:
            values = [implicit] if isinstance(implicit, str) else list(_as_sequence(implicit))
            unknown = [v for v in values if v not in flag_question.option_ids()]
            if unknown:
                errors.append(f"{sid}/{flag.id}: у вопроса '{flag.question}' нет опций {unknown}")
        else:
            check_condition(flag.when, f"red_flag {flag.id}")

    default_rules = [r for r in scenario.routing if r.is_default]
    if not default_rules:
        errors.append(f"{sid}: в routing нет default-правила — маршрут может остаться неопределён")
    if len(default_rules) > 1:
        errors.append(f"{sid}: в routing больше одного default-правила")
    if scenario.routing and not scenario.routing[-1].is_default:
        errors.append(f"{sid}: default-правило должно быть последним в routing")

    for idx, rule in enumerate(scenario.routing):
        if rule.when is not None:
            check_condition(rule.when, f"routing[{idx}]")
        if rule.outcome is Outcome.RECOVERY_PLAN:
            if not rule.plan:
                errors.append(f"{sid}/routing[{idx}]: outcome=recovery_plan требует поле plan")
            elif rule.plan not in scenario.plans:
                errors.append(f"{sid}/routing[{idx}]: план '{rule.plan}' не описан в plans")

    for plan in scenario.plans.values():
        stage_keys = [s.key for s in plan.stages]
        if len(set(stage_keys)) != len(stage_keys):
            errors.append(f"{sid}/plan {plan.key}: дублирующиеся stage.key")
        for stage in plan.stages:
            task_keys = [t.key for t in stage.tasks]
            if len(set(task_keys)) != len(task_keys):
                errors.append(f"{sid}/plan {plan.key}/{stage.key}: дублирующиеся task.key")
            if stage.advance_if.is_empty:
                errors.append(
                    f"{sid}/plan {plan.key}/{stage.key}: advance_if пуст — этап не завершится"
                )

    unused_plans = set(scenario.plans) - {r.plan for r in scenario.routing if r.plan}
    if unused_plans:
        errors.append(
            f"{sid}: планы не используются ни одним routing-правилом: {sorted(unused_plans)}"
        )

    if not raw.get("entry_hints"):
        errors.append(f"{sid}: entry_hints пуст — классификатору не на что опереться")

    return errors


def load_scenario_file(path: Path, validator: Draft202012Validator | None = None) -> Scenario:
    validator = validator or _load_schema()
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ScenarioValidationError([f"{path.name}: файл пуст или не является объектом"])

    schema_errors = [
        f"{path.name}: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(raw)
    ]
    if schema_errors:
        raise ScenarioValidationError(schema_errors)

    scenario = _build_scenario(raw)
    semantic_errors = _validate_semantics(scenario, raw)
    if semantic_errors:
        raise ScenarioValidationError(semantic_errors)
    return scenario


def load_registry(defs_dir: Path) -> ScenarioRegistry:
    """Загружает все *.yaml из каталога сценариев (рекурсивно)."""
    validator = _load_schema()
    files = sorted(p for p in defs_dir.rglob("*.yaml") if p.is_file())
    if not files:
        raise ScenarioValidationError([f"В {defs_dir} нет ни одного сценария"])

    scenarios: dict[str, Scenario] = {}
    errors: list[str] = []
    for path in files:
        try:
            scenario = load_scenario_file(path, validator)
        except ScenarioValidationError as exc:
            errors.extend(exc.errors)
            continue
        if scenario.id in scenarios:
            errors.append(f"Дублирующийся id сценария: {scenario.id} ({path.name})")
            continue
        scenarios[scenario.id] = scenario

    if errors:
        raise ScenarioValidationError(errors)
    return ScenarioRegistry(scenarios=scenarios)
