from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

from core.domain.entities import Checkin
from core.domain.enums import Feeling
from core.domain.scenario import CheckinCondition, Plan, PlanTask, Scenario, Stage
from core.scenarios.plan_engine import (
    DEFAULT_ESCALATION,
    TrackerAction,
    decide,
    evaluate_checkin_condition,
)
from core.scenarios.snapshot import plan_from_snapshot, plan_to_snapshot

PLAN_ID = uuid4()


def make_checkins(feelings: list[Feeling], stage_index: int = 0, tasks: int = 0) -> list[Checkin]:
    """Свежие первыми, как их отдаёт репозиторий."""
    today = date(2026, 1, 10)
    return [
        Checkin(
            plan_id=PLAN_ID,
            date=today - timedelta(days=i),
            stage_index=stage_index,
            feeling=feeling,
            tasks_done=[f"t{n}" for n in range(tasks)],
        )
        for i, feeling in enumerate(feelings)
    ]


class TestCheckinCondition:
    def test_consecutive_not_reached(self) -> None:
        cond = CheckinCondition(feeling=(Feeling.BETTER,), consecutive=2)
        checkins = make_checkins([Feeling.BETTER])
        assert not evaluate_checkin_condition(cond, checkins, days_on_stage=1, task_count=3)

    def test_consecutive_reached(self) -> None:
        cond = CheckinCondition(feeling=(Feeling.BETTER,), consecutive=2)
        checkins = make_checkins([Feeling.BETTER, Feeling.BETTER, Feeling.WORSE])
        assert evaluate_checkin_condition(cond, checkins, days_on_stage=2, task_count=3)

    def test_streak_broken_by_older_is_irrelevant(self) -> None:
        cond = CheckinCondition(feeling=(Feeling.WORSE,), consecutive=2)
        checkins = make_checkins([Feeling.WORSE, Feeling.BETTER, Feeling.WORSE])
        assert not evaluate_checkin_condition(cond, checkins, days_on_stage=3, task_count=3)

    def test_min_days_blocks(self) -> None:
        cond = CheckinCondition(feeling=(Feeling.BETTER,), consecutive=1, min_days=3)
        checkins = make_checkins([Feeling.BETTER])
        assert not evaluate_checkin_condition(cond, checkins, days_on_stage=1, task_count=1)
        assert evaluate_checkin_condition(cond, checkins, days_on_stage=3, task_count=1)

    def test_tasks_ratio(self) -> None:
        cond = CheckinCondition(feeling=(Feeling.BETTER,), consecutive=2, tasks_done_ratio_gte=0.6)
        weak = make_checkins([Feeling.BETTER, Feeling.BETTER], tasks=1)
        strong = make_checkins([Feeling.BETTER, Feeling.BETTER], tasks=3)
        assert not evaluate_checkin_condition(cond, weak, days_on_stage=2, task_count=4)
        assert evaluate_checkin_condition(cond, strong, days_on_stage=2, task_count=4)

    def test_empty_condition_never_fires(self) -> None:
        assert not evaluate_checkin_condition(
            CheckinCondition(), make_checkins([Feeling.BETTER]), days_on_stage=5, task_count=1
        )


def build_plan(escalate: CheckinCondition | None) -> Plan:
    stage = Stage(
        key="acute",
        title="Острая фаза",
        days=3,
        tasks=(PlanTask(key="ice", text="Лёд"),),
        advance_if=CheckinCondition(feeling=(Feeling.BETTER, Feeling.SAME), consecutive=2),
        escalate_if=escalate,
    )
    second = Stage(
        key="mobility",
        title="Подвижность",
        days=3,
        tasks=(PlanTask(key="walk", text="Ходьба"),),
        advance_if=CheckinCondition(feeling=(Feeling.BETTER,), consecutive=1),
        escalate_if=escalate,
    )
    return Plan(key="p", title="План", stages=(stage, second), completion_text="Готово")


class TestDecide:
    def test_stays_when_nothing_matches(self) -> None:
        plan = build_plan(None)
        result = decide(
            plan,
            0,
            stage_checkins=make_checkins([Feeling.SAME]),
            all_checkins=make_checkins([Feeling.SAME]),
            days_on_stage=1,
        )
        assert result.action is TrackerAction.STAY

    def test_advances(self) -> None:
        plan = build_plan(None)
        checkins = make_checkins([Feeling.BETTER, Feeling.SAME])
        result = decide(plan, 0, stage_checkins=checkins, all_checkins=checkins, days_on_stage=2)
        assert result.action is TrackerAction.ADVANCE
        assert result.next_stage_index == 1

    def test_completes_on_last_stage(self) -> None:
        plan = build_plan(None)
        checkins = make_checkins([Feeling.BETTER], stage_index=1)
        result = decide(plan, 1, stage_checkins=checkins, all_checkins=checkins, days_on_stage=2)
        assert result.action is TrackerAction.COMPLETE

    def test_escalates_on_two_worse(self) -> None:
        plan = build_plan(None)  # без escalate_if — работает DEFAULT_ESCALATION
        checkins = make_checkins([Feeling.WORSE, Feeling.WORSE])
        result = decide(plan, 0, stage_checkins=checkins, all_checkins=checkins, days_on_stage=2)
        assert result.action is TrackerAction.ESCALATE

    def test_escalation_beats_advance(self) -> None:
        """Если бы условия совпали одновременно, эскалация приоритетнее."""
        plan = build_plan(CheckinCondition(feeling=(Feeling.BETTER,), consecutive=2))
        checkins = make_checkins([Feeling.BETTER, Feeling.BETTER])
        result = decide(plan, 0, stage_checkins=checkins, all_checkins=checkins, days_on_stage=2)
        assert result.action is TrackerAction.ESCALATE

    def test_escalation_crosses_stages(self) -> None:
        """Ухудшение считается по всей истории, а не только по текущему этапу."""
        plan = build_plan(None)
        stage_checkins = make_checkins([Feeling.WORSE], stage_index=1)
        all_checkins = [
            *stage_checkins,
            *make_checkins([Feeling.WORSE], stage_index=0),
        ]
        result = decide(
            plan, 1, stage_checkins=stage_checkins, all_checkins=all_checkins, days_on_stage=1
        )
        assert result.action is TrackerAction.ESCALATE

    def test_default_escalation_is_two_worse(self) -> None:
        assert DEFAULT_ESCALATION.feeling == (Feeling.WORSE,)
        assert DEFAULT_ESCALATION.consecutive == 2


class TestSnapshot:
    def test_roundtrip_preserves_plan(self, ankle: Scenario) -> None:
        plan = ankle.plans["ankle_sprain_basic"]
        snapshot = plan_to_snapshot(ankle, plan)
        restored = plan_from_snapshot(snapshot)
        assert restored == plan

    def test_snapshot_keeps_scenario_version(self, ankle: Scenario) -> None:
        snapshot = plan_to_snapshot(ankle, ankle.plans["ankle_sprain_basic"])
        assert snapshot["scenario_version"] == ankle.version
        assert snapshot["scenario_id"] == ankle.id
