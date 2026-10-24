"""Расчёт прохождения программы. Чистая логика, без I/O — поэтому легко тестируется.

Правила взяты из ТЗ и важны дословно:

* доля считается по завершённым обязательным занятиям текущей версии плана;
* частичное выполнение показывается отдельно и в зачёт не идёт;
* если полный объём ещё не задан — показываем прогресс этапа без общего процента;
* отсутствие записи за день отображается как «нет данных», а не как пропуск;
* приём БАДов в процент не входит и учитывается отдельно;
* процент прохождения программы не равен проценту восстановления;
* завершение обозначается как «Программа пройдена», без вывода о выздоровлении.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from core.domain.entities import PlanItemLog, WellbeingLog
from core.domain.enums import ItemKind, ItemStatus
from core.domain.scenario import CheckinCondition, Plan

#: Что идёт в зачёт программы. БАДы намеренно не входят — требование ТЗ.
COUNTED_KINDS = (ItemKind.EXERCISE, ItemKind.TASK)

FEELING_WORDS = {"better": "лучше", "same": "без изменений", "worse": "хуже"}


class DayMark(StrEnum):
    DONE = "done"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    NO_DATA = "no_data"


@dataclass(frozen=True, slots=True)
class DayCell:
    date: date
    mark: DayMark


@dataclass(frozen=True, slots=True)
class WellbeingTrend:
    """Сравнение с началом программы и с предыдущим периодом."""

    first_pain: int | None = None
    last_pain: int | None = None
    previous_pain: int | None = None

    @property
    def since_start(self) -> int | None:
        if self.first_pain is None or self.last_pain is None:
            return None
        return self.last_pain - self.first_pain

    @property
    def since_previous(self) -> int | None:
        if self.previous_pain is None or self.last_pain is None:
            return None
        return self.last_pain - self.previous_pain


@dataclass(frozen=True, slots=True)
class ProgressView:
    plan_title: str
    stage_index: int
    stage_total: int
    stage_title: str
    completed_sessions: int
    partial_sessions: int
    skipped_sessions: int
    no_data_days: int
    #: None — полный объём программы ещё не задан, общий процент не показываем.
    total_sessions: int | None
    stage_day: int
    stage_days: int
    calendar: tuple[DayCell, ...]
    trend: WellbeingTrend
    next_checkpoint: str
    program_completed: bool = False

    @property
    def percent(self) -> int | None:
        if not self.total_sessions:
            return None
        return round(self.completed_sessions / self.total_sessions * 100)


def day_mark(logs: Sequence[PlanItemLog]) -> DayMark:
    """Как считается день.

    Полностью выполненный — все отмеченные обязательные пункты «выполнено».
    Хотя бы одно «частично» или смесь — частичный, и он в зачёт не идёт.
    """
    counted = [log for log in logs if log.item_kind in COUNTED_KINDS]
    if not counted:
        return DayMark.NO_DATA

    statuses = {log.status for log in counted}
    if statuses == {ItemStatus.DONE}:
        return DayMark.DONE
    if statuses == {ItemStatus.SKIPPED}:
        return DayMark.SKIPPED
    return DayMark.PARTIAL


def build_calendar(logs: Sequence[PlanItemLog], start: date, end: date) -> tuple[DayCell, ...]:
    """Календарь без дыр: день без записи — это «нет данных», а не пропуск."""
    by_day: dict[date, list[PlanItemLog]] = {}
    for log in logs:
        by_day.setdefault(log.date, []).append(log)

    cells: list[DayCell] = []
    current = start
    while current <= end:
        cells.append(DayCell(date=current, mark=day_mark(by_day.get(current, []))))
        current += timedelta(days=1)
    return tuple(cells)


def condition_words(condition: CheckinCondition) -> str:
    """Условие перехода человеческим языком — иначе «ближайшая цель» непонятна."""
    if condition.is_empty:
        return "условие перехода задаёт специалист"

    parts: list[str] = []
    if condition.feeling:
        feelings = ", ".join(FEELING_WORDS.get(f.value, f.value) for f in condition.feeling)
        if condition.consecutive > 1:
            parts.append(f"{condition.consecutive} дня подряд самочувствие «{feelings}»")
        else:
            parts.append(f"самочувствие «{feelings}»")
    if condition.min_days is not None:
        parts.append(f"не меньше {condition.min_days} дней на этапе")
    if condition.tasks_done_ratio_gte is not None:
        percent = round(condition.tasks_done_ratio_gte * 100)
        parts.append(f"выполнено не меньше {percent}% задач")
    return "; ".join(parts)


def wellbeing_trend(logs: Sequence[WellbeingLog]) -> WellbeingTrend:
    if not logs:
        return WellbeingTrend()
    ordered = sorted(logs, key=lambda log: log.date)
    previous = ordered[-2].pain_0_10 if len(ordered) > 1 else None
    return WellbeingTrend(
        first_pain=ordered[0].pain_0_10,
        last_pain=ordered[-1].pain_0_10,
        previous_pain=previous,
    )


def total_sessions(definition: Plan) -> int | None:
    """Полный объём программы в днях или None, если он не задан."""
    days = sum(stage.days for stage in definition.stages)
    return days or None


def build_progress(
    definition: Plan,
    *,
    stage_index: int,
    item_logs: Sequence[PlanItemLog],
    wellbeing_logs: Sequence[WellbeingLog],
    started_on: date,
    today: date,
    stage_started_on: date,
    completed: bool = False,
) -> ProgressView:
    calendar = build_calendar(item_logs, started_on, today)
    index = min(stage_index, len(definition.stages) - 1)
    stage = definition.stages[index]

    next_stage = definition.stages[index + 1] if index + 1 < len(definition.stages) else None
    if completed:
        checkpoint = "программа пройдена"
    elif next_stage is not None:
        checkpoint = f"переход на этап «{next_stage.title}»: {condition_words(stage.advance_if)}"
    else:
        checkpoint = f"завершение программы: {condition_words(stage.advance_if)}"

    return ProgressView(
        plan_title=definition.title,
        stage_index=index,
        stage_total=len(definition.stages),
        stage_title=stage.title,
        completed_sessions=sum(1 for cell in calendar if cell.mark is DayMark.DONE),
        partial_sessions=sum(1 for cell in calendar if cell.mark is DayMark.PARTIAL),
        skipped_sessions=sum(1 for cell in calendar if cell.mark is DayMark.SKIPPED),
        no_data_days=sum(1 for cell in calendar if cell.mark is DayMark.NO_DATA),
        total_sessions=total_sessions(definition),
        stage_day=max(1, min((today - stage_started_on).days + 1, stage.days)),
        stage_days=stage.days,
        calendar=calendar,
        trend=wellbeing_trend(wellbeing_logs),
        next_checkpoint=checkpoint,
        program_completed=completed,
    )
