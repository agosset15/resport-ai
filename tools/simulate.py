"""Консольный прогон сценария без Telegram, БД и LLM.

Нужен для ревью контента: врач или заказчик проходит дерево вопросов и видит,
к какому исходу ведёт каждая комбинация ответов, а затем — как ведёт себя трекер.

    uv run python -m tools.simulate
    uv run python -m tools.simulate --scenario football.ankle_sprain
    uv run python -m tools.simulate --scenario football.ankle_sprain --answers today,cannot
    uv run python -m tools.simulate --sample 3000 --all
    uv run python -m tools.simulate --sample 3000 --policy benign --json
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from core.config import get_settings
from core.domain.entities import Checkin
from core.domain.enums import Feeling, Outcome
from core.domain.scenario import Question, Scenario, ScenarioRegistry
from core.scenarios.engine import AskQuestion, ScenarioEngine, TriageDecision
from core.scenarios.loader import condition_question_refs, load_registry
from core.scenarios.plan_engine import TrackerAction, decide

PLAN_ID = uuid4()
COVERAGE_LIMIT = 200_000
FEELING_KEYS = {"1": Feeling.BETTER, "2": Feeling.SAME, "3": Feeling.WORSE}


#: Опции, которые «благополучный» пользователь выбирает чаще всего. Политика benign
#: приближает реальное распределение лучше, чем равномерный выбор: у каждого
#: скринера 1–2 экстренных варианта из 4–5, поэтому uniform завышает долю red flags.
BENIGN_OPTIONS = (
    "absent",
    "improving",
    "mild_decreasing",
    "walked",
    "sleep_ok",
    "accessible",
    "adult",
    "adult_involved",
    "inward",
    "soft_outside",
    "ready",
    "agreed",
    "load_only",
    "none",
    "no",
)


@dataclass
class Args:
    scenario: str | None
    answers: str | None
    coverage: bool
    sample: int | None
    policy: str
    unknown_rate: float
    seed: int
    all_scenarios: bool
    as_json: bool


def parse_args() -> Args:
    parser = argparse.ArgumentParser(description="Прогон сценария в консоли")
    parser.add_argument("--scenario", help="id сценария, например football.ankle_sprain")
    parser.add_argument("--answers", help="option_id через запятую — неинтерактивный прогон")
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="перебрать все комбинации ответов (только для коротких сценариев)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        help="число случайных проходов по графу вопросов вместо полного перебора",
    )
    parser.add_argument(
        "--policy",
        default="uniform",
        choices=("uniform", "benign", "unknown_heavy"),
        help="как выбирается ответ: равномерно, самый безобидный, с долей «не знаю»",
    )
    parser.add_argument(
        "--unknown-rate",
        type=float,
        default=0.3,
        help="доля ответов «не знаю» для политики unknown_heavy",
    )
    parser.add_argument("--seed", type=int, default=42, help="зерно генератора")
    parser.add_argument(
        "--all", action="store_true", dest="all_scenarios", help="прогнать все сценарии"
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="вывод в JSON")
    parsed = parser.parse_args()
    return Args(
        parsed.scenario,
        parsed.answers,
        parsed.coverage,
        parsed.sample,
        parsed.policy,
        parsed.unknown_rate,
        parsed.seed,
        parsed.all_scenarios,
        parsed.as_json,
    )


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


def risky_options(scenario: Scenario) -> dict[str, set[str]]:
    """question_key -> option_id, которые задевают red flag или путь к специалисту."""
    risky: dict[str, set[str]] = {}

    def add(question_key: str, option_ids: list[str]) -> None:
        risky.setdefault(question_key, set()).update(option_ids)

    for flag in scenario.red_flags:
        implicit = flag.when.get("equals") or flag.when.get("in")
        if implicit is not None:
            if isinstance(implicit, str):
                add(flag.question, [implicit])
            elif isinstance(implicit, list):
                add(flag.question, [str(v) for v in implicit])
        else:
            for key, options in condition_question_refs(flag.when):
                add(key, options)

    for rule in scenario.routing:
        if rule.outcome is not Outcome.REFER_SPECIALIST or rule.when is None:
            continue
        for key, options in condition_question_refs(rule.when):
            add(key, options)
    return risky


def pick_option(
    question: Question,
    rng: random.Random,
    policy: str,
    unknown_rate: float,
    risky: dict[str, set[str]],
) -> str:
    """Выбор ответа согласно политике. Неизвестной опции не придумываем."""
    option_ids = question.option_ids()
    if policy == "unknown_heavy" and "unknown" in option_ids and rng.random() < unknown_rate:
        return "unknown"
    if policy in ("benign", "unknown_heavy"):
        dangerous = risky.get(question.key, set())
        safe = [o for o in option_ids if o not in dangerous and o != "unknown"]
        if safe:
            # Из безопасных берём тот, что выглядит «ничего особенного».
            for candidate in BENIGN_OPTIONS:
                if candidate in safe:
                    return candidate
            return safe[0]
        # Все варианты задевают правила — честно отвечаем «не знаю».
        return "unknown" if "unknown" in option_ids else option_ids[-1]
    return rng.choice(option_ids)


def walk(
    engine: ScenarioEngine,
    rng: random.Random,
    policy: str,
    unknown_rate: float,
    risky: dict[str, set[str]],
) -> tuple[TriageDecision, int]:
    """Один проход по графу. Учитывает ask_if и обрыв опроса красным флагом."""
    answers: dict[str, str] = {}
    while True:
        step = engine.step(answers)
        if isinstance(step, TriageDecision):
            return step, len(answers)
        answers[step.question.key] = pick_option(step.question, rng, policy, unknown_rate, risky)


def sample_outcomes(engine: ScenarioEngine, args: Args) -> dict[str, Any]:
    """Распределение исходов по случайным проходам.

    Полный перебор (--coverage) на боевых сценариях неприменим: 24 вопроса по 3–5 опций
    дают ~10**14 комбинаций, и он к тому же игнорирует ask_if, то есть считает
    недостижимые наборы ответов.
    """
    rng = random.Random(args.seed)
    risky = risky_options(engine.scenario)
    total = args.sample or 1000
    outcomes: dict[str, int] = {}
    reasons: dict[str, int] = {}
    tiers: dict[str, int] = {}
    asked: list[int] = []

    for _ in range(total):
        decision, question_count = walk(engine, rng, args.policy, args.unknown_rate, risky)
        asked.append(question_count)
        outcomes[decision.outcome.value] = outcomes.get(decision.outcome.value, 0) + 1
        reason = decision.reason_codes[0] if decision.reason_codes else "-"
        reasons[reason] = reasons.get(reason, 0) + 1
        tier = "rf_emergency" if decision.triggered_flags else reason.split("_", 1)[0]
        tiers[tier] = tiers.get(tier, 0) + 1

    return {
        "scenario_id": engine.scenario.id,
        "declared_questions": len(engine.scenario.questions),
        "walks": total,
        "policy": args.policy,
        "outcomes": {k: v / total for k, v in sorted(outcomes.items())},
        "tiers": {k: v / total for k, v in sorted(tiers.items(), key=lambda kv: -kv[1])},
        "reasons": {k: v / total for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])},
        "asked_mean": round(statistics.mean(asked), 1),
        "asked_median": int(statistics.median(asked)),
        "asked_max": max(asked),
    }


def print_sample(stats: dict[str, Any]) -> None:
    print(f"\n{stats['scenario_id']}  (политика {stats['policy']}, {stats['walks']} проходов)")
    print(
        f"  вопросов объявлено: {stats['declared_questions']}, "
        f"задано в среднем {stats['asked_mean']}, "
        f"медиана {stats['asked_median']}, максимум {stats['asked_max']}"
    )
    for outcome, share in stats["outcomes"].items():
        print(f"  {outcome:<20} {share:6.1%}")
    print("  по тирам: " + ", ".join(f"{k} {v:.0%}" for k, v in stats["tiers"].items()))


def print_coverage(engine: ScenarioEngine) -> None:
    """Все комбинации ответов и куда они ведут — карта сценария для ревью."""
    questions = engine.scenario.questions
    combos = math.prod(len(q.options) for q in questions)
    if combos > COVERAGE_LIMIT:
        raise SystemExit(
            f"Полный перебор здесь неприменим: {combos:.3g} комбинаций "
            f"(предел {COVERAGE_LIMIT:.3g}). Используй --sample."
        )
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


def print_sample_total(report: list[dict[str, Any]]) -> None:
    if len(report) < 2:
        return
    shares: dict[str, float] = {}
    for stats in report:
        for outcome, share in stats["outcomes"].items():
            shares[outcome] = shares.get(outcome, 0.0) + share
    print("\n" + "=" * 60)
    print(f"ИТОГО по {len(report)} сценариям:")
    for outcome, total in sorted(shares.items()):
        print(f"  {outcome:<20} {total / len(report):6.1%}")
    asked = [stats["asked_mean"] for stats in report]
    print(f"  вопросов задано в среднем: {round(statistics.mean(asked), 1)}")
    print("=" * 60)


def main() -> None:
    args = parse_args()
    registry = load_registry(get_settings().content.scenarios_dir)

    if args.sample:
        ids = registry.ids() if args.all_scenarios else (args.scenario,)
        if ids == (None,):
            raise SystemExit("Укажи --scenario или --all")
        report = [
            sample_outcomes(ScenarioEngine(registry.require(sid)), args)
            for sid in ids
            if sid is not None
        ]
        if args.as_json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for stats in report:
                print_sample(stats)
            print_sample_total(report)
        return

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
