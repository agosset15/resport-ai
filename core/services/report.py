"""Отчёт за период: что было в плане, что выполнено, как менялось самочувствие.

Отчёт для пользователя в первую очередь: он видит свой прогресс и при желании
передаёт отчёт врачу. Вопросы к приёму собираются из данных детерминированно —
бот не придумывает медицинские выводы, а показывает, что видно по записям.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from uuid import UUID

from core.domain.entities import PlanItemLog, RecoveryPlan, WellbeingLog
from core.domain.enums import (
    EventType,
    ItemKind,
    ItemStatus,
    PlanSource,
    PlanStatus,
)
from core.domain.supplement import SupplementRegistry
from core.scenarios.snapshot import plan_from_snapshot, snapshot_text
from core.services.progress import build_progress
from core.services.protocols import (
    AdverseReactionRepository,
    EventRepository,
    PlanItemRepository,
    PlanRevisionRepository,
    SessionRepository,
    SupplementIntakeRepository,
    WellbeingRepository,
)
from core.services.tracker import local_today

SWELLING_WORDS = {
    "none": "отёка нет",
    "mild": "небольшой",
    "moderate": "умеренный",
    "severe": "сильный",
}

STATUS_WORDS = {
    "active": "принимает",
    "declined": "отказался",
    "stopped": "прекратил",
}

CAPACITY_WORDS = {
    "full": "всё как обычно",
    "limited": "кое-что труднее",
    "minimal": "многое не получается",
}


@dataclass(frozen=True, slots=True)
class WellbeingRow:
    date: date
    pain_0_10: int
    swelling: str
    daily_capacity: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class SupplementRow:
    """Строка журнала приёма добавки. Включается в отчёт только по флагу пользователя."""

    product: str
    taken_days: int
    skipped_days: int
    status: str
    reactions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportView:
    plan_title: str
    source: PlanSource
    scenario_title: str
    period_start: date
    period_end: date
    generated_at: datetime
    revisions: int
    stage_lines: tuple[str, ...]
    completed_sessions: int
    partial_sessions: int
    skipped_sessions: int
    no_data_days: int
    total_sessions: int | None
    percent: int | None
    program_completed: bool
    wellbeing: tuple[WellbeingRow, ...] = ()
    questions: tuple[str, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)
    supplements: tuple[SupplementRow, ...] = ()

    @property
    def filename_stem(self) -> str:
        return f"report_{self.period_start:%Y%m%d}_{self.period_end:%Y%m%d}"


def build_questions(
    item_logs: Sequence[PlanItemLog],
    wellbeing_logs: Sequence[WellbeingLog],
    *,
    titles: dict[str, str] | None = None,
) -> tuple[str, ...]:
    """Вопросы к приёму из записей, без медицинских выводов."""
    titles = titles or {}
    questions: list[str] = []

    ordered = sorted(wellbeing_logs, key=lambda log: log.date)
    if len(ordered) >= 2:
        first, last = ordered[0], ordered[-1]
        if last.pain_0_10 >= first.pain_0_10:
            questions.append(
                f"Боль не уменьшилась за период: была {first.pain_0_10} из 10, "
                f"стала {last.pain_0_10} из 10. С чем это может быть связано?"
            )
    if ordered and ordered[-1].swelling.value in ("moderate", "severe"):
        questions.append("Отёк сохраняется. Нужно ли что-то менять в нагрузке?")

    skipped = [log for log in item_logs if log.status is ItemStatus.SKIPPED]
    if skipped:
        names = sorted({titles.get(log.item_key, log.item_key) for log in skipped})[:3]
        questions.append("Не получается выполнять: " + ", ".join(names) + ". Чем заменить?")

    partial = [log for log in item_logs if log.status is ItemStatus.PARTIAL]
    if len(partial) >= 3:
        questions.append(
            "Часть упражнений получается только частично. Нагрузка подобрана правильно?"
        )

    commented = [log.comment for log in item_logs if log.comment]
    if commented:
        questions.append("Есть мои комментарии к упражнениям — посмотрите их в отчёте.")

    questions.append("Можно ли увеличивать нагрузку и когда возвращаться к тренировкам?")
    return tuple(questions)


class ReportService:
    def __init__(
        self,
        items: PlanItemRepository,
        wellbeing: WellbeingRepository,
        revisions: PlanRevisionRepository,
        sessions: SessionRepository,
        events: EventRepository,
        supplements: SupplementRegistry,
        intakes: SupplementIntakeRepository,
        reactions: AdverseReactionRepository,
    ) -> None:
        self._items = items
        self._wellbeing = wellbeing
        self._revisions = revisions
        self._sessions = sessions
        self._events = events
        self._supplements = supplements
        self._intakes = intakes
        self._reactions = reactions

    async def build(
        self,
        plan: RecoveryPlan,
        *,
        days: int = 14,
        timezone: str | None = None,
    ) -> ReportView:
        end = local_today(timezone)
        start = plan.started_at.date() if plan.started_at else end
        period_start = max(start, end.fromordinal(end.toordinal() - days + 1))

        definition = plan_from_snapshot(plan.plan_snapshot)
        item_logs = await self._items.for_period(plan.id, period_start, end)
        wellbeing_logs = await self._wellbeing.for_period(plan.id, period_start, end)
        revisions = await self._revisions.for_plan(plan.id)

        progress = build_progress(
            definition,
            stage_index=plan.current_stage,
            item_logs=item_logs,
            wellbeing_logs=wellbeing_logs,
            started_on=period_start,
            today=end,
            stage_started_on=(
                plan.stage_started_at.date() if plan.stage_started_at else period_start
            ),
            completed=plan.status is PlanStatus.COMPLETED,
        )

        titles = {
            exercise_id: str(card.get("title", exercise_id))
            for exercise_id, card in (plan.plan_snapshot.get("exercises") or {}).items()
        }
        titles.update({task.key: task.text for stage in definition.stages for task in stage.tasks})

        stage_lines = tuple(
            f"{index + 1}. {stage.title} — {stage.days} дн."
            + (" (текущий)" if index == progress.stage_index else "")
            for index, stage in enumerate(definition.stages)
        )

        view = ReportView(
            plan_title=definition.title,
            source=plan.source,
            scenario_title=snapshot_text(plan.plan_snapshot, "scenario_title", definition.title)
            or str(plan.plan_snapshot.get("scenario_title", definition.title)),
            period_start=period_start,
            period_end=end,
            generated_at=datetime.now(UTC),
            revisions=len(revisions),
            stage_lines=stage_lines,
            completed_sessions=progress.completed_sessions,
            partial_sessions=progress.partial_sessions,
            skipped_sessions=progress.skipped_sessions,
            no_data_days=progress.no_data_days,
            total_sessions=progress.total_sessions,
            percent=progress.percent,
            program_completed=progress.program_completed,
            wellbeing=tuple(
                WellbeingRow(
                    date=log.date,
                    pain_0_10=log.pain_0_10,
                    swelling=SWELLING_WORDS.get(log.swelling.value, log.swelling.value),
                    daily_capacity=CAPACITY_WORDS.get(
                        log.daily_capacity.value, log.daily_capacity.value
                    ),
                    note=log.note,
                )
                for log in sorted(wellbeing_logs, key=lambda log: log.date)
            ),
            questions=build_questions(item_logs, wellbeing_logs, titles=titles),
            notes=tuple(
                f"{log.date:%d.%m}: {titles.get(log.item_key, log.item_key)} — {log.comment}"
                for log in item_logs
                if log.comment
            ),
        )

        session = await self._sessions.get(plan.session_id)
        if session is not None:
            view = replace(
                view,
                supplements=await self._supplement_rows(session.user_id, item_logs),
            )

        await self._events.add(
            EventType.REPORT_BUILT,
            user_id=session.user_id if session else None,
            session_id=plan.session_id,
            payload={"plan_id": str(plan.id), "days": days},
        )
        return view

    async def _supplement_rows(
        self, user_id: UUID, item_logs: Sequence[PlanItemLog]
    ) -> tuple[SupplementRow, ...]:
        """Журнал приёма добавок. Только те курсы, которые пользователь разрешил включать."""
        all_reactions = await self._reactions.for_user(user_id)
        rows: list[SupplementRow] = []
        for intake in await self._intakes.for_user(user_id):
            if not intake.include_in_report:
                continue
            supplement = self._supplements.get(intake.supplement_id)
            if supplement is None:
                continue
            logs = [
                log
                for log in item_logs
                if log.item_kind is ItemKind.SUPPLEMENT and log.item_key == intake.supplement_id
            ]
            rows.append(
                SupplementRow(
                    product=supplement.product,
                    taken_days=sum(1 for log in logs if log.status is ItemStatus.DONE),
                    skipped_days=sum(1 for log in logs if log.status is ItemStatus.SKIPPED),
                    status=STATUS_WORDS.get(intake.status.value, intake.status.value),
                    reactions=tuple(
                        f"{reaction.created_at:%d.%m}: {reaction.text}"
                        if reaction.created_at
                        else reaction.text
                        for reaction in all_reactions
                        if reaction.supplement_id == intake.supplement_id
                    ),
                )
            )
        return tuple(rows)


def report_markdown(view: ReportView) -> str:
    """Текстовая версия отчёта. Она же уходит файлом, если шрифта для PDF нет."""
    source_word = (
        "назначение специалиста"
        if view.source is PlanSource.PRESCRIPTION
        else "сценарий, проверенный специалистами"
    )
    lines = [
        "# Отчёт о восстановлении",
        "",
        f"Период: {view.period_start:%d.%m.%Y} — {view.period_end:%d.%m.%Y}",
        f"Сформирован: {view.generated_at:%d.%m.%Y %H:%M} UTC",
        "",
        f"**Травма:** {view.scenario_title}",
        f"**План:** {view.plan_title}",
        f"**Источник плана:** {source_word}",
    ]
    if view.revisions:
        lines.append(f"**План менялся:** {view.revisions} раз(а)")

    lines += ["", "## Выполнение", ""]
    if view.percent is None:
        lines.append(f"- Пройдено занятий: {view.completed_sessions}")
        lines.append("- Полный объём программы не задан, общий процент не считается")
    else:
        lines.append(
            f"- Пройдено {view.completed_sessions} из {view.total_sessions} занятий "
            f"— {view.percent}% программы"
        )
    lines += [
        f"- Частично выполнено: {view.partial_sessions} (в зачёт программы не идёт)",
        f"- Пропущено: {view.skipped_sessions}",
        f"- Нет данных: {view.no_data_days}",
    ]
    if view.program_completed:
        lines.append("- Программа пройдена")

    lines += ["", "## Этапы", ""]
    lines += [f"- {line}" for line in view.stage_lines]

    lines += ["", "## Самочувствие", ""]
    if view.wellbeing:
        lines.append("| Дата | Боль 0–10 | Отёк | Повседневные дела |")
        lines.append("|---|---|---|---|")
        for row in view.wellbeing:
            lines.append(
                f"| {row.date:%d.%m} | {row.pain_0_10} | {row.swelling} | {row.daily_capacity} |"
            )
        with_notes = [row for row in view.wellbeing if row.note]
        if with_notes:
            lines += ["", "Заметки:"]
            lines += [f"- {row.date:%d.%m}: {row.note}" for row in with_notes]
    else:
        lines.append("Записей за период нет.")

    if view.notes:
        lines += ["", "## Комментарии к упражнениям", ""]
        lines += [f"- {note}" for note in view.notes]

    if view.supplements:
        lines += ["", "## Добавки", ""]
        lines.append("| Продукт | Принято дней | Пропущено | Статус |")
        lines.append("|---|---|---|---|")
        for supplement_row in view.supplements:
            lines.append(
                f"| {supplement_row.product} | {supplement_row.taken_days} "
                f"| {supplement_row.skipped_days} | {supplement_row.status} |"
            )
        reactions = [
            text for supplement_row in view.supplements for text in supplement_row.reactions
        ]
        if reactions:
            lines += ["", "Сообщения о нежелательных реакциях:"]
            lines += [f"- {text}" for text in reactions]
        lines += [
            "",
            "Приём добавок в процент прохождения программы не входит и учитывается",
            "отдельно.",
        ]

    lines += ["", "## Вопросы к приёму", ""]
    lines += [f"{index}. {q}" for index, q in enumerate(view.questions, start=1)]

    lines += [
        "",
        "---",
        "",
        "Отчёт собран ботом по отметкам пользователя. Это не диагноз и не медицинское",
        "заключение. Процент прохождения программы — про выполненные занятия, а не про",
        "то, насколько зажила травма.",
    ]
    return "\n".join(lines) + "\n"
