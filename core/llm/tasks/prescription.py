"""Задача 4: разложить назначение специалиста на пункты плана.

Модель здесь ничего не придумывает и ничего не подменяет: она только разбивает текст
назначения на отдельные пункты и вытаскивает ограничения и срок. Формулировки остаются
дословными — ТЗ прямо требует согласовывать изменения назначенной нагрузки со
специалистом, поэтому сопоставлять назначение с упражнениями из нашей библиотеки нельзя:
это подменило бы дозировки врача нашими.

При недоступности модели работает детерминированный фоллбэк: текст режется по строкам.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from core.domain.enums import LlmTask
from core.llm.runner import LlmRunner
from core.llm.schemas import PrescriptionPlan

SYSTEM = """Ты разбираешь назначение специалиста по восстановлению на отдельные пункты.

Правила:
- Переноси формулировки дословно. Не переписывай, не упрощай, не улучшай.
- Ничего не добавляй от себя: ни упражнений, ни подходов, ни повторений, ни сроков.
- Если дозировка указана — оставь её внутри пункта как есть.
- items — конкретные действия из назначения, по одному на пункт.
- limits — только то, что названо ограничением или запретом.
- duration_days — срок, если он прямо указан числом; иначе null.
- Ты не врач: не оцениваешь назначение и не даёшь рекомендаций.
- Отвечай строго в заданной JSON-схеме."""

MAX_ITEMS = 15
MIN_ITEM_LENGTH = 3

_SPLIT_RE = re.compile(r"[\n;•]+|(?<=\.)\s+(?=[А-ЯA-Z])")


@dataclass(frozen=True, slots=True)
class Prescription:
    items: tuple[str, ...]
    limits: tuple[str, ...] = ()
    duration_days: int | None = None
    #: Разобрано без модели — показываем пользователю, что это его текст как есть.
    from_fallback: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.items


def split_plainly(text: str) -> Prescription:
    """Фоллбэк без модели: пункт на строку. Ничего не теряем и ничего не добавляем."""
    parts = [part.strip(" -–—\t") for part in _SPLIT_RE.split(text)]
    items = [part for part in parts if len(part) >= MIN_ITEM_LENGTH][:MAX_ITEMS]
    return Prescription(items=tuple(items), from_fallback=True)


def _user_prompt(text: str) -> str:
    return f"Назначение специалиста:\n{text.strip()}"


async def parse_prescription(
    runner: LlmRunner,
    text: str,
    *,
    session_id: UUID | None = None,
) -> Prescription:
    """Разбор назначения. Никогда не возвращает пустоту: есть детерминированный фоллбэк."""
    if not text.strip():
        return Prescription(items=())

    result = await runner.run(
        LlmTask.PARSE_PRESCRIPTION,
        system=SYSTEM,
        user=_user_prompt(text),
        model_cls=PrescriptionPlan,
        session_id=session_id,
    )
    if result is None or not result.items:
        return split_plainly(text)

    return Prescription(
        items=tuple(item.strip() for item in result.items[:MAX_ITEMS] if item.strip()),
        limits=tuple(limit.strip() for limit in result.limits if limit.strip()),
        duration_days=result.duration_days,
    )
