"""Консольный прогон сценария без Telegram, БД и LLM.

Нужен для ревью контента: врач или заказчик проходит дерево вопросов и видит,
к какому исходу ведёт каждая комбинация ответов, а затем — как ведёт себя трекер.

    uv run python -m tools.simulate
    uv run python -m tools.simulate --scenario football.ankle_sprain
    uv run python -m tools.simulate --scenario football.ankle_sprain --answers today,cannot
"""

from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import uuid4

from core.config import get_settings
from core.domain.entities import Checkin
from core.domain.enums import Feeling, Outcome
from core.domain.scenario import Scenario, ScenarioRegistry
from core.scenarios.engine import AskQuestion, ScenarioEngine, TriageDecision
from core.scenarios.loader import load_registry
from core.scenarios.plan_engine import TrackerAction, decide

PLAN_ID = uuid4()
FEELING_KEYS = {"1": Feeling.BETTER, "2": Feeling.SAME, "3": Feeling.WORSE}


@dataclass
class Args:
    scenario: str | None
    answers: str | None
    coverage: bool


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description="Прогон сценария в консоли")
    parser.add_argument("--scenario", help="id сценария, например football.ankle_sprain")
    parser.add_argument("--answers", help="option_id через запятую — неинтерактивный прогон")
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="перебрать все комбинации ответов и показать распределение исходов",
    )
    parsed = parser.parse_args()
    return Args(parsed.scenario, parsed.answers, parsed.coverage)


def choose_scenario(registry: ScenarioRegistry, scenario_id: str | None) -> Scenario:
    if scenario_id:
        return registry.require(scenario_id)
    ids = registry.ids()
    print("Доступные сценарии:")
    for index, sid in enumerate(ids, start=1):
        scenario = registry.require(sid)
        print(f"  {index}. {sid} — {scenario.title}")
    while True:
        raw = input("Номер сценария: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(ids):
            return registry.require(ids[int(raw) - 1])
        print("Не понял, нужен номер из списка.")


def run_survey(engine: ScenarioEngine, scripted: list[str] | None) -> TriageDecision:
    answers: dict[str, str] = {}
    queue = list(scripted or [])

    while True:
        step = engine.step(answers)
        if isinstance(step, TriageDecision):
            return step

        assert isinstance(step, AskQuestion)
        question = step.question
        print(f"\nВопрос {step.asked_count} из {step.total_count}: {question.text}")
        if question.hint:
            print(f"  ({question.hint})")
        for index, option in enumerate(question.options, start=1):
            print(f"  {index}. {option.label}  [{option.id}]")

        if queue:
            choice = queue.pop(0)
            if choice not in question.option_ids():
                raise SystemExit(f"У вопроса {question.key} нет варианта '{choice}'")
            print(f"  -> {choice}")
            answers[question.key] = choice
            continue

        raw = input("Ответ (номер или option_id): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(question.options):
            answers[question.key] = question.options[int(raw) - 1].id
        elif raw in question.option_ids():
            answers[question.key] = raw
        else:
            print("Не понял, повторю вопрос.")


def print_decision(scenario: Scenario, decision: TriageDecision) -> None:
    print("\n" + "=" * 60)
    print(f"Исход: {decision.outcome.value}")
    print(f"Коды причин: {', '.join(decision.reason_codes) or 'нет'}")
    if decision.triggered_flags:
        print(f"Red flags: {', '.join(decision.triggered_flags)}")
        for flag in scenario.red_flags:
            if flag.id in decision.triggered_flags:
                print(f"  причина: {flag.reason}")
    print("=" * 60)

    if decision.outcome is Outcome.REFER_SPECIALIST:
        print("\nТекст пользователю (фоллбэк без LLM):")
        print(scenario.texts.refer_specialist.strip())
    else:
        print("\nТекст пользователю (фоллбэк без LLM):")
        print(scenario.texts.recovery_plan_intro.strip())


def run_tracker(scenario: Scenario, plan_key: str) -> None:
    plan = scenario.plans[plan_key]
    stage_index = 0
    day = date.today()
    history: list[Checkin] = []

    print(f"\nПлан: {plan.title} — {len(plan.stages)} этап(ов)")
    while True:
        stage = plan.stages[stage_index]
        print(
            f"\n--- Этап {stage_index + 1}/{len(plan.stages)}: {stage.title} ({stage.days} дн.) ---"
        )
        if stage.description:
            print(stage.description)
        for task in stage.tasks:
            print(f"  • {task.text}")

        raw = input("Самочувствие [1 лучше / 2 без изменений / 3 хуже / q выход]: ").strip()
        if raw.lower() in {"q", "exit", ""}:
            return
        feeling = FEELING_KEYS.get(raw)
        if feeling is None:
            print("Не понял.")
            continue

        checkin = Checkin(
            plan_id=PLAN_ID,
            date=day,
            stage_index=stage_index,
            feeling=feeling,
            tasks_done=[t.key for t in stage.tasks],
        )
        history.insert(0, checkin)
        day += timedelta(days=1)

        stage_history = [c for c in history if c.stage_index == stage_index]
        days_on_stage = len(stage_history)
        result = decide(
            plan,
            stage_index,
            stage_checkins=stage_history,
            all_checkins=history,
            days_on_stage=days_on_stage,
        )
        print(f"  решение движка: {result.action.value} ({result.reason})")

        if result.action is TrackerAction.ESCALATE:
            print("\n" + scenario.texts.escalation.strip())
            return
        if result.action is TrackerAction.COMPLETE:
            print("\n" + plan.completion_text.strip())
            return
        if result.action is TrackerAction.ADVANCE:
            stage_index = result.next_stage_index or stage_index


def print_coverage(engine: ScenarioEngine) -> None:
    """Все комбинации ответов и куда они ведут — карта сценария для ревью."""
    questions = engine.scenario.questions
    counter: dict[tuple[str, str], int] = {}
    total = 0

    for combo in itertools.product(*(q.option_ids() for q in questions)):
        answers = dict(zip((q.key for q in questions), combo, strict=True))
        decision = engine.route(answers)
        key = (decision.outcome.value, decision.reason_codes[0] if decision.reason_codes else "-")
        counter[key] = counter.get(key, 0) + 1
        total += 1

    print(f"\nКомбинаций ответов: {total}")
    print(f"{'исход':<20} {'причина':<25} {'кол-во':>7}  доля")
    for (outcome, reason), count in sorted(counter.items(), key=lambda kv: -kv[1]):
        print(f"{outcome:<20} {reason:<25} {count:>7}  {count / total:.0%}")


def main() -> None:
    args = parse_args()
    registry = load_registry(get_settings().content.scenarios_dir)
    scenario = choose_scenario(registry, args.scenario)
    engine = ScenarioEngine(scenario)

    print(f"\n{scenario.title} ({scenario.id} v{scenario.version})")

    if args.coverage:
        print_coverage(engine)
        return

    scripted = [a.strip() for a in args.answers.split(",")] if args.answers else None
    decision = run_survey(engine, scripted)
    print_decision(scenario, decision)

    if decision.outcome is Outcome.RECOVERY_PLAN and decision.plan_key:
        if scripted is not None:
            return
        run_tracker(scenario, decision.plan_key)


if __name__ == "__main__":
    main()
