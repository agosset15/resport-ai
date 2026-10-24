"""Подбор БАДов: детерминированный, без LLM, с жёсткими стопами.

Правила ТЗ, по которым написан этот модуль:

* автоматические рекомендации доступны совершеннолетним при достаточных данных;
* при беременности, грудном вскармливании, предстоящей операции, возможном
  взаимодействии с лекарствами или неясной безопасности подбор **приостанавливается**
  до консультации специалиста;
* подтверждение прочтения предупреждения эти ограничения **не отменяет** — поэтому
  функции «снять стоп» здесь нет вообще;
* одного совпадения со сценарием травмы недостаточно для рекомендации конкретной
  добавки, поэтому подбор вообще не смотрит на сценарий: он смотрит только на
  проверенную базу и ответы анкеты;
* бот не диагностирует дефициты по описанию травмы — здесь нет и не должно быть
  логики «травма → нужный нутриент».

Любой приём лекарств считается возможным взаимодействием. Это сознательно грубо:
проверенной базы взаимодействий у нас нет, а FDA прямо предупреждает, что добавки
могут взаимодействовать с лекарствами и быть опасными во время операции.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from core.domain.supplement import MIN_ADULT_AGE, Supplement, SupplementRegistry
from core.scenarios.matching import tokens
from core.supplements.intake_form import SupplementProfile


class StopReason(StrEnum):
    """Почему подбор приостановлен целиком."""

    PROFILE_INCOMPLETE = "profile_incomplete"
    AGE_UNKNOWN = "age_unknown"
    MINOR = "minor"
    PREGNANCY = "pregnancy"
    BREASTFEEDING = "breastfeeding"
    UPCOMING_SURGERY = "upcoming_surgery"
    MEDICATIONS = "medications"


class ExcludeReason(StrEnum):
    """Почему отброшен конкретный продукт."""

    NOT_APPROVED = "not_approved"
    ALLERGEN = "allergen"
    CONTRAINDICATION = "contraindication"
    DUPLICATE_COMPONENT = "duplicate_component"
    MIN_AGE = "min_age"


@dataclass(frozen=True, slots=True)
class Excluded:
    supplement: Supplement
    reason: ExcludeReason
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Selection:
    stops: tuple[StopReason, ...] = ()
    recommended: tuple[Supplement, ...] = ()
    excluded: tuple[Excluded, ...] = ()

    @property
    def is_suspended(self) -> bool:
        return bool(self.stops)

    @property
    def has_recommendations(self) -> bool:
        return bool(self.recommended) and not self.is_suspended


def _overlaps(needles: Sequence[str], haystack: Sequence[str]) -> str | None:
    """Пересечение по основам слов. Нарочно широкое: ложный пропуск здесь опаснее.

    Возвращает сработавшую пару текстом — её показываем пользователю, чтобы решение
    бота было объяснимым.
    """
    haystack_tokens = {token for item in haystack for token in tokens(item)}
    if not haystack_tokens:
        return None
    for needle in needles:
        needle_tokens = tokens(needle)
        if needle_tokens & haystack_tokens:
            return needle
    return None


def find_stops(profile: SupplementProfile) -> tuple[StopReason, ...]:
    """Жёсткие стопы. Снять их нельзя ничем, кроме изменения самих ответов."""
    stops: list[StopReason] = []

    if profile.age is None:
        stops.append(StopReason.AGE_UNKNOWN)
    elif profile.age < MIN_ADULT_AGE:
        stops.append(StopReason.MINOR)

    # Неотвеченный вопрос — это не «нет». Неясная безопасность тоже останавливает подбор.
    if profile.pregnant is None or profile.breastfeeding is None:
        if StopReason.PROFILE_INCOMPLETE not in stops:
            stops.append(StopReason.PROFILE_INCOMPLETE)
    if profile.pregnant:
        stops.append(StopReason.PREGNANCY)
    if profile.breastfeeding:
        stops.append(StopReason.BREASTFEEDING)

    if profile.upcoming_surgery is None:
        if StopReason.PROFILE_INCOMPLETE not in stops:
            stops.append(StopReason.PROFILE_INCOMPLETE)
    elif profile.upcoming_surgery:
        stops.append(StopReason.UPCOMING_SURGERY)

    if profile.medications:
        stops.append(StopReason.MEDICATIONS)

    return tuple(stops)


def taken_components(already_taking: Sequence[Supplement]) -> tuple[str, ...]:
    return tuple(
        component for supplement in already_taking for component in supplement.component_names()
    )


def select(
    registry: SupplementRegistry,
    profile: SupplementProfile,
    *,
    already_taking: Sequence[Supplement] = (),
) -> Selection:
    """Что можно предложить. При стопах рекомендаций нет вообще."""
    stops = find_stops(profile)

    recommended: list[Supplement] = []
    excluded: list[Excluded] = []
    taken = taken_components(already_taking)
    taken_ids = {supplement.id for supplement in already_taking}

    for supplement in registry.supplements.values():
        if supplement.id in taken_ids:
            continue

        if not supplement.is_recommendable:
            excluded.append(Excluded(supplement, ExcludeReason.NOT_APPROVED))
            continue

        if profile.age is not None and profile.age < supplement.min_age:
            excluded.append(Excluded(supplement, ExcludeReason.MIN_AGE, str(supplement.min_age)))
            continue

        hit = _overlaps(supplement.allergens, profile.allergies)
        if hit is not None:
            excluded.append(Excluded(supplement, ExcludeReason.ALLERGEN, hit))
            continue

        hit = _overlaps(supplement.contraindications, profile.conditions)
        if hit is not None:
            excluded.append(Excluded(supplement, ExcludeReason.CONTRAINDICATION, hit))
            continue

        hit = _overlaps(supplement.component_names(), taken)
        if hit is not None:
            excluded.append(Excluded(supplement, ExcludeReason.DUPLICATE_COMPONENT, hit))
            continue

        recommended.append(supplement)

    # При стопе рекомендации не показываются, но причины отбора сохраняем:
    # они нужны для отладки и для отчёта, а не для пользователя.
    return Selection(
        stops=stops,
        recommended=() if stops else tuple(recommended),
        excluded=tuple(excluded),
    )
