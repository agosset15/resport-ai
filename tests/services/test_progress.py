"""Расчёт прогресса. Правила ТЗ проверяются дословно, они не косметические.

Ключевые: частичное выполнение не идёт в зачёт, день без записи — это «нет данных»,
а не пропуск, без заданного объёма общий процент не показывается, и приём БАДов
в процент не входит.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest

from core.domain.entities import PlanItemLog, WellbeingLog
from core.domain.enums import (
    DailyCapacity,
    Feeling,
    ItemKind,
    ItemStatus,
    Swelling,
)
from core.domain.scenario import CheckinCondition, Plan, PlanTask, Stage
from core.services.progress import (
    DayMark,
    build_calendar,
    build_progress,
    condition_words,
    day_mark,
    total_sessions,
    wellbeing_trend,
)

PLAN_ID = uuid4()
START = date(2026, 10, 18)


def item(day_offset: int, status: ItemStatus, key: str = "a", kind: ItemKind = ItemKind.EXERCISE):
    return PlanItemLog(
        plan_id=PLAN_ID,
        date=START + timedelta(days=day_offset),
        item_kind=kind,
        item_key=key,
        status=status,
    )


def wellbeing(day_offset: int, pain: int) -> WellbeingLog:
    return WellbeingLog(
        plan_id=PLAN_ID,
        date=START + timedelta(days=day_offset),
        pain_0_10=pain,
        swelling=Swelling.MILD,
        daily_capacity=DailyCapacity.LIMITED,
    )


def two_stage_plan() -> Plan:
    stage = Stage(
        key="relief",
        title="Снять нагрузку",
        days=3,
        tasks=(PlanTask(key="rest", text="Покой"),),
        exercises=("a",),
        advance_if=CheckinCondition(feeling=(Feeling.BETTER,), consecutive=2, min_days=2),
    )
    second = Stage(
        key="load",
        title="Возвращение нагрузки",
        days=7,
        tasks=(PlanTask(key="walk", text="Ходьба"),),
        advance_if=CheckinCondition(
            feeling=(Feeling.BETTER,), consecutive=3, tasks_done_ratio_gte=0.7
        ),
    )
    return Plan(key="p", title="План", stages=(stage, second), completion_text="Готово")


class TestDayMark:
    def test_all_done(self) -> None:
        assert day_mark([item(0, ItemStatus.DONE), item(0, ItemStatus.DONE, "b")]) is DayMark.DONE

    def test_mixed_is_partial(self) -> None:
        logs = [item(0, ItemStatus.DONE), item(0, ItemStatus.SKIPPED, "b")]
        assert day_mark(logs) is DayMark.PARTIAL

    def test_any_partial_is_partial(self) -> None:
        assert day_mark([item(0, ItemStatus.PARTIAL)]) is DayMark.PARTIAL

    def test_all_skipped(self) -> None:
        assert day_mark([item(0, ItemStatus.SKIPPED)]) is DayMark.SKIPPED

    def test_no_logs_is_no_data(self) -> None:
        assert day_mark([]) is DayMark.NO_DATA

    def test_supplements_do_not_count(self) -> None:
        """Приём БАДов учитывается отдельно и в зачёт программы не идёт."""
        logs = [item(0, ItemStatus.DONE, "vit_d", ItemKind.SUPPLEMENT)]
        assert day_mark(logs) is DayMark.NO_DATA


class TestCalendar:
    def test_gaps_are_no_data_not_skips(self) -> None:
        calendar = build_calendar([item(0, ItemStatus.DONE)], START, START + timedelta(days=2))
        assert [cell.mark for cell in calendar] == [
            DayMark.DONE,
            DayMark.NO_DATA,
            DayMark.NO_DATA,
        ]

    def test_covers_whole_period(self) -> None:
        calendar = build_calendar([], START, START + timedelta(days=6))
        assert len(calendar) == 7


class TestProgress:
    def test_percent_counts_only_completed_days(self) -> None:
        logs = [
            item(0, ItemStatus.DONE),
            item(1, ItemStatus.DONE),
            item(2, ItemStatus.PARTIAL),
            item(3, ItemStatus.SKIPPED),
        ]
        view = build_progress(
            two_stage_plan(),
            stage_index=0,
            item_logs=logs,
            wellbeing_logs=[],
            started_on=START,
            today=START + timedelta(days=3),
            stage_started_on=START,
        )
        assert view.total_sessions == 10
        assert view.completed_sessions == 2
        assert view.partial_sessions == 1
        assert view.skipped_sessions == 1
        assert view.percent == 20

    def test_partial_is_not_counted_as_done(self) -> None:
        view = build_progress(
            two_stage_plan(),
            stage_index=0,
            item_logs=[item(0, ItemStatus.PARTIAL)],
            wellbeing_logs=[],
            started_on=START,
            today=START,
            stage_started_on=START,
        )
        assert view.completed_sessions == 0
        assert view.partial_sessions == 1
        assert view.percent == 0

    def test_no_total_means_no_percent(self) -> None:
        """«Если полный объём ещё не задан, показывать прогресс этапа без процента»."""
        empty = Plan(key="p", title="План", stages=(), completion_text="")
        assert total_sessions(empty) is None

        stage = Stage(
            key="s",
            title="Этап",
            days=5,
            tasks=(PlanTask(key="t", text="Задача"),),
            advance_if=CheckinCondition(feeling=(Feeling.BETTER,)),
        )
        one = Plan(key="p", title="План", stages=(stage,), completion_text="")
        view = build_progress(
            one,
            stage_index=0,
            item_logs=[],
            wellbeing_logs=[],
            started_on=START,
            today=START,
            stage_started_on=START,
        )
        assert view.total_sessions == 5
        assert view.percent == 0

    def test_next_checkpoint_names_the_next_stage(self) -> None:
        view = build_progress(
            two_stage_plan(),
            stage_index=0,
            item_logs=[],
            wellbeing_logs=[],
            started_on=START,
            today=START,
            stage_started_on=START,
        )
        assert "Возвращение нагрузки" in view.next_checkpoint

    def test_completed_program_says_so(self) -> None:
        view = build_progress(
            two_stage_plan(),
            stage_index=1,
            item_logs=[],
            wellbeing_logs=[],
            started_on=START,
            today=START,
            stage_started_on=START,
            completed=True,
        )
        assert view.program_completed
        assert view.next_checkpoint == "программа пройдена"


class TestConditionWords:
    def test_feeling_streak(self) -> None:
        words = condition_words(CheckinCondition(feeling=(Feeling.BETTER,), consecutive=3))
        assert "3 дня подряд" in words
        assert "лучше" in words

    def test_ratio_in_percent(self) -> None:
        words = condition_words(CheckinCondition(tasks_done_ratio_gte=0.7))
        assert "70%" in words

    def test_min_days(self) -> None:
        assert "2 дней" in condition_words(CheckinCondition(min_days=2))

    def test_empty_condition(self) -> None:
        assert "специалист" in condition_words(CheckinCondition())


class TestWellbeingTrend:
    def test_compares_with_start_and_previous(self) -> None:
        trend = wellbeing_trend([wellbeing(0, 7), wellbeing(2, 5), wellbeing(4, 3)])
        assert trend.first_pain == 7
        assert trend.last_pain == 3
        assert trend.since_start == -4
        assert trend.since_previous == -2

    def test_single_record_has_no_previous(self) -> None:
        trend = wellbeing_trend([wellbeing(0, 6)])
        assert trend.since_start == 0
        assert trend.since_previous is None

    def test_no_records(self) -> None:
        trend = wellbeing_trend([])
        assert trend.last_pain is None
        assert trend.since_start is None

    @pytest.mark.parametrize("unordered", [True, False])
    def test_order_does_not_matter(self, unordered: bool) -> None:
        logs = [wellbeing(0, 8), wellbeing(3, 4)]
        if unordered:
            logs.reverse()
        assert wellbeing_trend(logs).since_start == -4
