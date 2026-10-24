"""Подбор БАДов, журнал приёма и нежелательные реакции.

LLM в подборе не участвует вообще: решение принимает `core/supplements/matcher.py`
по проверенной базе и ответам анкеты. Сервис только носит данные между репозиториями
и движком подбора.

Отметки приёма пишутся в plan_item_logs с `ItemKind.SUPPLEMENT`, поэтому они автоматически
не попадают в процент прохождения программы — так требует ТЗ.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from core.domain.entities import AdverseReaction, PlanItemLog, RecoveryPlan, User
from core.domain.enums import (
    EventType,
    ItemKind,
    ItemStatus,
    ReactionSeverity,
    SupplementStatus,
)
from core.domain.supplement import Supplement, SupplementRegistry
from core.services.protocols import (
    AdverseReactionRepository,
    EventRepository,
    PlanItemRepository,
    SupplementIntakeRepository,
    SupplementProfileRepository,
)
from core.services.tracker import local_today
from core.supplements.intake_form import SupplementProfile
from core.supplements.matcher import Selection, select

#: Слова, по которым сообщение о реакции считается тяжёлым. Лучше перестраховаться:
#: цена ложного срабатывания — лишний совет вызвать помощь.
SEVERE_MARKERS = (
    "дыш",
    "задыха",
    "отёк лица",
    "отек лица",
    "отёк горла",
    "отек горла",
    "горло",
    "язык",
    "сыпь по всему",
    "крапивниц",
    "обморок",
    "сознани",
    "давление упало",
    "сердце",
    "анафилак",
)


def classify_severity(text: str) -> ReactionSeverity:
    """Грубая проверка по ключевым словам, не диагноз.

    Решение здесь влияет только на то, какой совет показать: обратиться за помощью
    или вызывать экстренную. Поэтому порог намеренно низкий.
    """
    lowered = text.casefold()
    if any(marker in lowered for marker in SEVERE_MARKERS):
        return ReactionSeverity.SEVERE
    return ReactionSeverity.MILD


class SupplementService:
    def __init__(
        self,
        registry: SupplementRegistry,
        profiles: SupplementProfileRepository,
        intakes: SupplementIntakeRepository,
        reactions: AdverseReactionRepository,
        items: PlanItemRepository,
        events: EventRepository,
    ) -> None:
        self._registry = registry
        self._profiles = profiles
        self._intakes = intakes
        self._reactions = reactions
        self._items = items
        self._events = events

    # --- анкета ---------------------------------------------------------------

    async def save_profile(self, user: User, profile: SupplementProfile) -> None:
        await self._profiles.upsert(user.id, profile.to_answers())
        await self._events.add(
            EventType.SUPPLEMENT_PROFILE_SAVED,
            user_id=user.id,
            payload={"complete": profile.is_complete},
        )

    async def get_profile(self, user: User) -> SupplementProfile | None:
        record = await self._profiles.get(user.id)
        return SupplementProfile.from_answers(record.answers) if record else None

    # --- подбор ---------------------------------------------------------------

    async def selection(self, user: User) -> Selection | None:
        """None — анкеты ещё нет, её надо пройти."""
        profile = await self.get_profile(user)
        if profile is None:
            return None

        active = await self._intakes.active_for_user(user.id)
        already = tuple(
            supplement
            for supplement in (self._registry.get(i.supplement_id) for i in active)
            if supplement is not None
        )
        result = select(self._registry, profile, already_taking=already)

        if result.is_suspended:
            await self._events.add(
                EventType.SUPPLEMENT_SELECTION_SUSPENDED,
                user_id=user.id,
                payload={"stops": [stop.value for stop in result.stops]},
            )
        elif result.recommended:
            await self._events.add(
                EventType.SUPPLEMENT_OFFERED,
                user_id=user.id,
                payload={"ids": [s.id for s in result.recommended]},
            )
        return result

    # --- курс приёма ----------------------------------------------------------

    async def add_to_plan(self, user: User, supplement: Supplement) -> None:
        await self._intakes.set_status(user.id, supplement.id, SupplementStatus.ACTIVE)
        await self._events.add(
            EventType.SUPPLEMENT_ADDED,
            user_id=user.id,
            payload={"supplement_id": supplement.id},
        )

    async def decline(self, user: User, supplement: Supplement) -> None:
        """Отказ фиксируется: он не снижает процент прохождения программы."""
        await self._intakes.set_status(user.id, supplement.id, SupplementStatus.DECLINED)
        await self._events.add(
            EventType.SUPPLEMENT_DECLINED,
            user_id=user.id,
            payload={"supplement_id": supplement.id},
        )

    async def stop(self, user: User, supplement_id: str) -> None:
        await self._intakes.set_status(user.id, supplement_id, SupplementStatus.STOPPED)
        await self._events.add(
            EventType.SUPPLEMENT_STOPPED,
            user_id=user.id,
            payload={"supplement_id": supplement_id},
        )

    async def active_supplements(self, user: User) -> tuple[Supplement, ...]:
        active = await self._intakes.active_for_user(user.id)
        return tuple(
            supplement
            for supplement in (self._registry.get(i.supplement_id) for i in active)
            if supplement is not None
        )

    # --- журнал приёма --------------------------------------------------------

    async def mark_taken(
        self,
        plan: RecoveryPlan,
        supplement_id: str,
        *,
        taken: bool,
        day: date | None = None,
        timezone: str | None = None,
    ) -> None:
        """Отметка приёма за день. Идёт в plan_item_logs, в процент программы не входит."""
        await self._items.upsert(
            PlanItemLog(
                plan_id=plan.id,
                date=day or local_today(timezone),
                item_kind=ItemKind.SUPPLEMENT,
                item_key=supplement_id,
                status=ItemStatus.DONE if taken else ItemStatus.SKIPPED,
            )
        )

    # --- нежелательные реакции ------------------------------------------------

    async def report_reaction(self, user: User, supplement_id: str, text: str) -> ReactionSeverity:
        """Фиксирует реакцию и останавливает курс. Возвращает оценку тяжести."""
        severity = classify_severity(text)
        await self._reactions.add(user.id, supplement_id, severity, text)
        await self._intakes.set_status(user.id, supplement_id, SupplementStatus.STOPPED)
        await self._events.add(
            EventType.ADVERSE_REACTION_REPORTED,
            user_id=user.id,
            payload={"supplement_id": supplement_id, "severity": severity.value},
        )
        return severity

    async def reactions_of(self, user_id: UUID) -> tuple[AdverseReaction, ...]:
        return tuple(await self._reactions.for_user(user_id))
