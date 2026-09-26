"""Задача 3: человеческое объяснение уже принятого решения.

Решение принимает движок. LLM только переформулирует его понятным языком. Если модель
недоступна или ответ невалиден — показываем статичный текст из YAML.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from core.domain.enums import LlmTask, Outcome
from core.domain.scenario import Scenario
from core.llm.runner import LlmRunner
from core.llm.schemas import ExplainStep
from core.scenarios.engine import TriageDecision

SYSTEM = """Ты объясняешь спортсмену готовое решение приложения. Решение уже принято
алгоритмом — менять его нельзя, можно только понятно пересказать.

Правила:
- Не ставь диагноз, не называй болезни, не назначай лечение и препараты.
- Не обещай сроки выздоровления.
- Если решение — обратиться к специалисту, не отговаривай и не смягчай.
- Если решение — план восстановления, не обещай, что всё точно заживёт само.
- 2–4 коротких предложения, обращение на «ты», без медицинского жаргона и эмодзи.
- Никаких новых рекомендаций сверх переданных данных.
- Отвечай строго в заданной JSON-схеме."""


def _user_prompt(
    scenario: Scenario,
    decision: TriageDecision,
    answers: Mapping[str, str],
    flag_reasons: Sequence[str],
) -> str:
    readable = []
    for question in scenario.questions:
        option_id = answers.get(question.key)
        if option_id is None:
            continue
        option = question.option(option_id)
        readable.append(f"- {question.text} — {option.label if option else option_id}")

    lines = [
        f"Сценарий: {scenario.title}",
        f"Решение алгоритма: {decision.outcome.value}",
        f"Коды причин: {', '.join(decision.reason_codes) or 'нет'}",
    ]
    if flag_reasons:
        lines.append("Сработавшие критерии безопасности:")
        lines += [f"- {reason}" for reason in flag_reasons]
    if readable:
        lines.append("Ответы спортсмена:")
        lines += readable
    if decision.outcome is Outcome.RECOVERY_PLAN and decision.plan_key:
        plan = scenario.plans.get(decision.plan_key)
        if plan is not None:
            lines.append(f"Предлагаемый план: {plan.title}, {len(plan.stages)} этапа(ов)")
    return "\n".join(lines)


async def explain_step(
    runner: LlmRunner,
    scenario: Scenario,
    decision: TriageDecision,
    answers: Mapping[str, str],
    *,
    session_id: UUID | None = None,
) -> str | None:
    """Возвращает текст или None (фоллбэк: scenario.texts)."""
    flag_reasons = [
        flag.reason for flag in scenario.red_flags if flag.id in decision.triggered_flags
    ]
    result = await runner.run(
        LlmTask.EXPLAIN_STEP,
        system=SYSTEM,
        user=_user_prompt(scenario, decision, answers, flag_reasons),
        model_cls=ExplainStep,
        session_id=session_id,
    )
    return result.text if result else None


def fallback_text(scenario: Scenario, decision: TriageDecision) -> str:
    if decision.outcome is Outcome.REFER_SPECIALIST:
        return scenario.texts.refer_specialist
    return scenario.texts.recovery_plan_intro
