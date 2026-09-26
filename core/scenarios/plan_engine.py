"""Правила трекера: когда переводить на следующий этап и когда эскалировать.

Эскалация детерминирована и работает даже если в YAML её забыли описать: без явного
`escalate_if` действует DEFAULT_ESCALATION. Трекер не должен удерживать человека от врача.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from core.domain.entities import Checkin
from core.domain.enums import Feeling
from core.domain.scenario import CheckinCondition, Plan, Stage

DEFAULT_ESCALATION = CheckinCondition(feeling=(Feeling.WORSE,), consecutive=2)


class TrackerAction(StrEnum):
    STAY = "stay"
    ADVANCE = "advance"
    COMPLETE = "complete"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class TrackerDecision:
    action: TrackerAction
    reason: str
    next_stage_index: int | None = None


def evaluate_checkin_condition(
    condition: CheckinCondition,
    recent: Sequence[Checkin],
    *,
    days_on_stage: int,
    task_count: int,
) -> bool:
    """`recent` — чек-ины от свежего к старому (в пределах нужного этапа)."""
    if condition.is_empty:
        return False

    if condition.min_days is not None and days_on_stage < condition.min_days:
        return False

    window = list(recent[: condition.consecutive])
    if len(window) < condition.consecutive:
        return False

    if condition.feeling and any(c.feeling not in condition.feeling for c in window):
        return False

    if condition.tasks_done_ratio_gte is not None:
        if task_count == 0:
            return False
        ratios = [len(set(c.tasks_done)) / task_count for c in window]
        if sum(ratios) / len(ratios) < condition.tasks_done_ratio_gte:
            return False

    return True


def escalation_condition(stage: Stage) -> CheckinCondition:
    return stage.escalate_if or DEFAULT_ESCALATION


def decide(
    plan: Plan,
    stage_index: int,
    *,
    stage_checkins: Sequence[Checkin],
    all_checkins: Sequence[Checkin],
    days_on_stage: int,
) -> TrackerDecision:
    """Что делать после очередного чек-ина.

    stage_checkins — чек-ины текущего этапа, свежие первыми.
    all_checkins   — вся история плана, свежие первыми (эскалация смотрит сквозь этапы).
    """
    stage = plan.stages[stage_index]
    task_count = len(stage.tasks)

    escalate = escalation_condition(stage)
    if evaluate_checkin_condition(
        escalate, all_checkins, days_on_stage=days_on_stage, task_count=task_count
    ):
        return TrackerDecision(
            action=TrackerAction.ESCALATE,
            reason=f"escalate_if:{stage.key}",
        )

    if evaluate_checkin_condition(
        stage.advance_if, stage_checkins, days_on_stage=days_on_stage, task_count=task_count
    ):
        next_index = stage_index + 1
        if next_index >= len(plan.stages):
            return TrackerDecision(action=TrackerAction.COMPLETE, reason=f"finished:{stage.key}")
        return TrackerDecision(
            action=TrackerAction.ADVANCE,
            reason=f"advance_if:{stage.key}",
            next_stage_index=next_index,
        )

    return TrackerDecision(action=TrackerAction.STAY, reason="conditions_not_met")
