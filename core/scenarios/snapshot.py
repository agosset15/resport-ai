"""Снимок плана восстановления.

План копируется в БД в момент выдачи (recovery_plans.plan_snapshot). Правка YAML не ломает
пользователей, которые уже находятся в середине восстановления: они доходят по своей копии.
"""

from __future__ import annotations

from typing import Any

from core.domain.enums import Feeling
from core.domain.exercise import Dosage, Exercise, ExerciseLibrary
from core.domain.scenario import CheckinCondition, Plan, PlanTask, Scenario, Stage

#: 1 — только задачи; 2 — вшитые карточки упражнений.
SNAPSHOT_FORMAT = 2


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


def _exercise_to_dict(exercise: Exercise) -> dict[str, Any]:
    return {
        "id": exercise.id,
        "title": exercise.title,
        "instruction": exercise.instruction,
        "lookup_hint": exercise.lookup_text(),
        "dosage": {
            "sets": exercise.dosage.sets,
            "reps": exercise.dosage.reps,
            "duration_seconds": exercise.dosage.duration_seconds,
            "note": exercise.dosage.note,
        },
        "limits": list(exercise.limits),
        "equipment": list(exercise.equipment),
        "body_region": exercise.body_region,
        "phase": exercise.phase,
        "review_status": exercise.review_status,
    }


def _exercise_from_dict(raw: dict[str, Any]) -> Exercise:
    dosage_raw = raw.get("dosage") or {}
    return Exercise(
        id=raw["id"],
        title=raw["title"],
        instruction=raw["instruction"],
        dosage=Dosage(
            sets=dosage_raw.get("sets"),
            reps=dosage_raw.get("reps"),
            duration_seconds=dosage_raw.get("duration_seconds"),
            note=dosage_raw.get("note"),
        ),
        body_region=raw.get("body_region", "general"),
        phase=raw.get("phase", "acute"),
        limits=tuple(raw.get("limits", [])),
        equipment=tuple(raw.get("equipment", [])),
        lookup_hint=raw.get("lookup_hint"),
        review_status=raw.get("review_status", "draft"),
    )


def exercises_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Exercise]:
    """Карточки упражнений из снимка.

    Берутся из снимка, а не из библиотеки: правка библиотеки не должна менять
    упражнения тому, кто уже идёт по плану. Снимок формата 1 упражнений не знает —
    для него возвращается пустой словарь.
    """
    raw = snapshot.get("exercises") or {}
    return {key: _exercise_from_dict(value) for key, value in raw.items()}


def plan_to_snapshot(
    scenario: Scenario, plan: Plan, library: ExerciseLibrary | None = None
) -> dict[str, Any]:
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
            "self_rehab_intro": scenario.texts.self_rehab_intro or "",
        },
        "exercises": {
            exercise_id: _exercise_to_dict(exercise)
            for exercise_id in {e for s in plan.stages for e in s.exercises}
            if library is not None and (exercise := library.get(exercise_id)) is not None
        },
        "stages": [
            {
                "key": stage.key,
                "title": stage.title,
                "days": stage.days,
                "description": stage.description,
                "tasks": [{"key": t.key, "text": t.text} for t in stage.tasks],
                "exercises": list(stage.exercises),
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
            exercises=tuple(s.get("exercises", [])),
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
