"""Снимок плана восстановления.

План копируется в БД в момент выдачи (recovery_plans.plan_snapshot). Правка YAML не ломает
пользователей, которые уже находятся в середине восстановления: они доходят по своей копии.
"""

from __future__ import annotations

from typing import Any

from core.domain.enums import Feeling
from core.domain.scenario import CheckinCondition, Plan, PlanTask, Scenario, Stage

SNAPSHOT_FORMAT = 1


def _condition_to_dict(condition: CheckinCondition | None) -> dict[str, Any] | None:
    if condition is None:
        return None
    return {
        "feeling": [f.value for f in condition.feeling],
        "consecutive": condition.consecutive,
        "min_days": condition.min_days,
        "tasks_done_ratio_gte": condition.tasks_done_ratio_gte,
    }


def _condition_from_dict(raw: dict[str, Any] | None) -> CheckinCondition | None:
    if raw is None:
        return None
    return CheckinCondition(
        feeling=tuple(Feeling(f) for f in raw.get("feeling", [])),
        consecutive=int(raw.get("consecutive", 1)),
        min_days=raw.get("min_days"),
        tasks_done_ratio_gte=raw.get("tasks_done_ratio_gte"),
    )


def plan_to_snapshot(scenario: Scenario, plan: Plan) -> dict[str, Any]:
    return {
        "format": SNAPSHOT_FORMAT,
        "scenario_id": scenario.id,
        "scenario_version": scenario.version,
        "scenario_title": scenario.title,
        "plan_key": plan.key,
        "title": plan.title,
        "completion_text": plan.completion_text,
        "texts": {
            "recovery_plan_intro": scenario.texts.recovery_plan_intro,
            "escalation": scenario.texts.escalation,
            "refer_specialist": scenario.texts.refer_specialist,
        },
        "stages": [
            {
                "key": stage.key,
                "title": stage.title,
                "days": stage.days,
                "description": stage.description,
                "tasks": [{"key": t.key, "text": t.text} for t in stage.tasks],
                "advance_if": _condition_to_dict(stage.advance_if),
                "escalate_if": _condition_to_dict(stage.escalate_if),
            }
            for stage in plan.stages
        ],
    }


def plan_from_snapshot(snapshot: dict[str, Any]) -> Plan:
    stages = tuple(
        Stage(
            key=s["key"],
            title=s["title"],
            days=int(s["days"]),
            description=s.get("description"),
            tasks=tuple(PlanTask(key=t["key"], text=t["text"]) for t in s["tasks"]),
            advance_if=_condition_from_dict(s.get("advance_if")) or CheckinCondition(),
            escalate_if=_condition_from_dict(s.get("escalate_if")),
        )
        for s in snapshot["stages"]
    )
    return Plan(
        key=snapshot["plan_key"],
        title=snapshot["title"],
        stages=stages,
        completion_text=snapshot["completion_text"],
    )


def snapshot_text(snapshot: dict[str, Any], key: str, default: str = "") -> str:
    texts = snapshot.get("texts") or {}
    value = texts.get(key)
    return value if isinstance(value, str) else default
