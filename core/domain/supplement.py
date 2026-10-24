"""Карточка БАДа и реестр. Только данные, без I/O.

Ключевое правило, из которого выросла вся структура: **бот не придумывает дозировки**.
Поля `intake.dose_text` и `intake.duration_text` переносятся дословно из проверенного
источника для конкретного продукта. Нет записи — нет рекомендации.

Пока запись не подписана (`review_status: draft`), подбор её не предложит: см.
`core/supplements/matcher.py`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: Маркер незаполненного поля. Запись с ним нельзя переводить в `approved`:
#: иначе бот покажет пользователю дозировку, которой никто не проверял.
UNFILLED = "НЕ ЗАПОЛНЕНО"

REVIEW_STATUSES = ("draft", "approved")

#: Совершеннолетие: автоматический подбор доступен только взрослым (требование ТЗ).
MIN_ADULT_AGE = 18


@dataclass(frozen=True, slots=True)
class Component:
    """Компонент состава. Количество — как на этикетке продукта."""

    name: str
    amount: str | None = None
    unit: str | None = None

    def human(self) -> str:
        if self.amount and self.unit:
            return f"{self.name} — {self.amount} {self.unit}"
        if self.amount:
            return f"{self.name} — {self.amount}"
        return self.name


@dataclass(frozen=True, slots=True)
class Intake:
    """Как принимать. Дословно из источника, без вычислений на нашей стороне."""

    dose_text: str
    duration_text: str

    @property
    def is_filled(self) -> bool:
        return UNFILLED not in self.dose_text and UNFILLED not in self.duration_text


@dataclass(frozen=True, slots=True)
class Interaction:
    """С чем взаимодействует: класс лекарств или компонент другой добавки."""

    with_what: str
    note: str


@dataclass(frozen=True, slots=True)
class Source:
    title: str
    url: str
    retrieved_at: str


@dataclass(frozen=True, slots=True)
class Supplement:
    id: str
    product: str
    manufacturer: str
    composition: tuple[Component, ...]
    rationale: str
    benefit_limits: str
    intake: Intake
    source: Source
    updated_at: str
    excipients: tuple[str, ...] = ()
    allergens: tuple[str, ...] = ()
    contraindications: tuple[str, ...] = ()
    side_effects: tuple[str, ...] = ()
    interactions: tuple[Interaction, ...] = ()
    adverse_reaction_actions: str = ""
    min_age: int = MIN_ADULT_AGE
    review_status: str = "draft"

    @property
    def needs_review(self) -> bool:
        return self.review_status != "approved"

    @property
    def is_recommendable(self) -> bool:
        """Предлагать можно только подписанную запись с заполненным приёмом."""
        return not self.needs_review and self.intake.is_filled

    def component_names(self) -> tuple[str, ...]:
        """Нормализованные названия компонентов — для проверки дублирования."""
        return tuple(component.name.strip().casefold() for component in self.composition)


@dataclass(frozen=True, slots=True)
class SupplementRegistry:
    supplements: Mapping[str, Supplement]

    def get(self, supplement_id: str) -> Supplement | None:
        return self.supplements.get(supplement_id)

    def require(self, supplement_id: str) -> Supplement:
        supplement = self.supplements.get(supplement_id)
        if supplement is None:
            raise KeyError(f"БАД не найден: {supplement_id}")
        return supplement

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.supplements))

    def recommendable(self) -> tuple[Supplement, ...]:
        return tuple(s for s in self.supplements.values() if s.is_recommendable)

    def drafts(self) -> tuple[Supplement, ...]:
        return tuple(s for s in self.supplements.values() if s.needs_review)
