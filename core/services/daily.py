"""План на сегодня: что делать и как отметить результат.

План собирается детерминированно из снимка текущего этапа — никакой генерации на лету.
Упражнения берутся из карточек, вшитых в снимок при выдаче плана, поэтому правка
библиотеки не меняет упражнения тому, кто уже идёт по программе.

Отметки «Выполнено / Частично / Пропущено» и комментарии живут отдельно от чек-ина:
чек-ин — это самочувствие за день, а здесь результат по каждому пункту.
"""

from __future__ import annotations

from datetime import date

from core.domain.entities import PlanItemLog, RecoveryPlan, WellbeingLog
from core.domain.enums import EventType, ItemKind, ItemStatus
from core.scenarios.snapshot import exercises_from_snapshot, plan_from_snapshot
from core.services.dto import DailyItem, DailyPlanView, WellbeingView
from core.services.protocols import (
    EventRepository,
    PlanItemRepository,
    SessionRepository,
    WellbeingRepository,
)
from core.services.tracker import local_today


class DailyPlanService:
    def __init__(
        self,
        items: PlanItemRepository,
        wellbeing: WellbeingRepository,
        sessions: SessionRepository,
        events: EventRepository,
    ) -> None:
        self._items = items
        self._wellbeing = wellbeing
        self._sessions = sessions
        self._events = events

    async def today(
        self,
        plan: RecoveryPlan,
        day: date | None = None,
        timezone: str | None = None,
    ) -> DailyPlanView:
        day = day or local_today(timezone)
        definition = plan_from_snapshot(plan.plan_snapshot)
        cards = exercises_from_snapshot(plan.plan_snapshot)

        index = min(plan.current_stage, len(definition.stages) - 1)
        stage = definition.stages[index]

        logs = {
            (log.item_kind, log.item_key): log for log in await self._items.for_date(plan.id, day)
        }

        items: list[DailyItem] = []
        for exercise_id in stage.exercises:
            card = cards.get(exercise_id)
            log = logs.get((ItemKind.EXERCISE, exercise_id))
            if card is None:
                # Снимок формата 1 карточек не знает: показываем хотя бы id, но
                # молча терять пункт плана нельзя.
                items.append(
                    DailyItem(
                        kind=ItemKind.EXERCISE,
                        key=exercise_id,
                        title=exercise_id,
                        status=log.status if log else None,
                        comment=log.comment if log else None,
                    )
                )
                continue
            items.append(
                DailyItem(
                    kind=ItemKind.EXERCISE,
                    key=exercise_id,
                    title=card.title,
                    instruction=card.instruction,
                    lookup_hint=card.lookup_text(),
                    dosage=card.dosage.human(),
                    limits=card.limits,
                    status=log.status if log else None,
                    comment=log.comment if log else None,
                )
            )

        for task in stage.tasks:
            log = logs.get((ItemKind.TASK, task.key))
            items.append(
                DailyItem(
                    kind=ItemKind.TASK,
                    key=task.key,
                    title=task.text,
                    status=log.status if log else None,
                    comment=log.comment if log else None,
                )
            )

        started = plan.stage_started_at or plan.started_at
        day_number = (day - started.date()).days + 1 if started else 1

        return DailyPlanView(
            plan_id=plan.id,
            plan_title=definition.title,
            date=day,
            stage_index=index,
            stage_total=len(definition.stages),
            stage_title=stage.title,
            stage_description=stage.description,
            day_number=max(1, min(day_number, stage.days)),
            day_total=stage.days,
            items=tuple(items),
            source=plan.source,
            wellbeing_done=await self._wellbeing.get_for_date(plan.id, day) is not None,
        )

    async def mark(
        self,
        plan: RecoveryPlan,
        *,
        kind: ItemKind,
        key: str,
        status: ItemStatus,
        comment: str | None = None,
        day: date | None = None,
        timezone: str | None = None,
    ) -> None:
        """Отметка по пункту. Повторная отметка за тот же день заменяет прежнюю."""
        day = day or local_today(timezone)
        await self._items.upsert(
            PlanItemLog(
                plan_id=plan.id,
                date=day,
                item_kind=kind,
                item_key=key,
                status=status,
                comment=comment,
            )
        )
        session = await self._sessions.get(plan.session_id)
        await self._events.add(
            EventType.PLAN_ITEM_MARKED,
            user_id=session.user_id if session else None,
            session_id=plan.session_id,
            payload={
                "plan_id": str(plan.id),
                "item_kind": kind.value,
                "item_key": key,
                "status": status.value,
                "has_comment": comment is not None,
            },
        )

    async def set_comment(
        self,
        plan: RecoveryPlan,
        *,
        kind: ItemKind,
        key: str,
        comment: str,
        day: date | None = None,
        timezone: str | None = None,
    ) -> None:
        """Комментарий без отметки: статус остаётся прежним или «частично»."""
        day = day or local_today(timezone)
        existing = {
            (log.item_kind, log.item_key): log for log in await self._items.for_date(plan.id, day)
        }
        current = existing.get((kind, key))
        await self._items.upsert(
            PlanItemLog(
                plan_id=plan.id,
                date=day,
                item_kind=kind,
                item_key=key,
                status=current.status if current else ItemStatus.PARTIAL,
                comment=comment,
            )
        )

    async def log_wellbeing(
        self,
        plan: RecoveryPlan,
        wellbeing: WellbeingView,
        day: date | None = None,
        timezone: str | None = None,
    ) -> None:
        """Запись самочувствия за день. Повторная запись за тот же день заменяет прежнюю."""
        day = day or local_today(timezone)
        await self._wellbeing.upsert(
            WellbeingLog(
                plan_id=plan.id,
                date=day,
                pain_0_10=max(0, min(10, wellbeing.pain_0_10)),
                swelling=wellbeing.swelling,
                daily_capacity=wellbeing.daily_capacity,
                note=wellbeing.note,
            )
        )
        session = await self._sessions.get(plan.session_id)
        await self._events.add(
            EventType.WELLBEING_LOGGED,
            user_id=session.user_id if session else None,
            session_id=plan.session_id,
            payload={
                "plan_id": str(plan.id),
                "pain_0_10": wellbeing.pain_0_10,
                "swelling": wellbeing.swelling.value,
                "daily_capacity": wellbeing.daily_capacity.value,
            },
        )

    async def item_of(
        self, plan: RecoveryPlan, kind: ItemKind, key: str, timezone: str | None = None
    ) -> DailyItem | None:
        view = await self.today(plan, timezone=timezone)
        return next((i for i in view.items if i.kind is kind and i.key == key), None)
