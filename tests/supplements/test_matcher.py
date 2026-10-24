"""Подбор БАДов. Здесь проверяются именно запреты, а не «счастливый путь».

Правила ТЗ, которые обязаны держаться:
* автоматический подбор — только совершеннолетним и только при достаточных данных;
* беременность, ГВ, предстоящая операция, лекарства и неясность — жёсткие стопы;
* подтверждение прочтения предупреждения стопы не отменяет;
* одного совпадения со сценарием травмы недостаточно — сценарий тут вообще не участвует;
* дублирование компонентов с уже принимаемым исключает продукт.
"""

from __future__ import annotations

import pytest

from core.domain.supplement import (
    Component,
    Intake,
    Source,
    Supplement,
    SupplementRegistry,
)
from core.supplements.intake_form import SupplementProfile
from core.supplements.matcher import (
    ExcludeReason,
    StopReason,
    find_stops,
    select,
)


def supplement(
    sid: str = "demo",
    *,
    components: tuple[str, ...] = ("Магний",),
    allergens: tuple[str, ...] = (),
    contraindications: tuple[str, ...] = (),
    approved: bool = True,
    filled: bool = True,
    min_age: int = 18,
) -> Supplement:
    return Supplement(
        id=sid,
        product=f"Продукт {sid}",
        manufacturer="Производитель",
        composition=tuple(Component(name=name) for name in components),
        rationale="Основание",
        benefit_limits="Пределы пользы",
        intake=Intake(
            dose_text="1 капсула в день" if filled else "НЕ ЗАПОЛНЕНО",
            duration_text="4 недели" if filled else "НЕ ЗАПОЛНЕНО",
        ),
        source=Source(title="Источник", url="https://example.test", retrieved_at="2026-10-24"),
        updated_at="2026-10-24",
        allergens=allergens,
        contraindications=contraindications,
        adverse_reaction_actions="Прекратить приём",
        min_age=min_age,
        review_status="approved" if approved else "draft",
    )


def registry(*items: Supplement) -> SupplementRegistry:
    return SupplementRegistry(supplements={item.id: item for item in items})


def adult(**overrides) -> SupplementProfile:
    base = {
        "age": 30,
        "pregnant": False,
        "breastfeeding": False,
        "upcoming_surgery": False,
    }
    base.update(overrides)
    return SupplementProfile(**base)


class TestHardStops:
    def test_adult_with_complete_profile_has_no_stops(self) -> None:
        assert find_stops(adult()) == ()

    def test_minor_is_stopped(self) -> None:
        assert StopReason.MINOR in find_stops(adult(age=16))

    def test_unknown_age_is_stopped(self) -> None:
        assert StopReason.AGE_UNKNOWN in find_stops(adult(age=None))

    def test_pregnancy_is_stopped(self) -> None:
        assert StopReason.PREGNANCY in find_stops(adult(pregnant=True))

    def test_breastfeeding_is_stopped(self) -> None:
        assert StopReason.BREASTFEEDING in find_stops(adult(breastfeeding=True))

    def test_upcoming_surgery_is_stopped(self) -> None:
        assert StopReason.UPCOMING_SURGERY in find_stops(adult(upcoming_surgery=True))

    def test_any_medication_is_stopped(self) -> None:
        """Проверенной базы взаимодействий нет, поэтому любое лекарство — стоп."""
        assert StopReason.MEDICATIONS in find_stops(adult(medications=("варфарин",)))

    @pytest.mark.parametrize("unanswered", ["pregnant", "breastfeeding", "upcoming_surgery"])
    def test_unanswered_question_is_not_a_no(self, unanswered: str) -> None:
        """Неотвеченный вопрос — это неясная безопасность, а не «нет»."""
        stops = find_stops(adult(**{unanswered: None}))
        assert StopReason.PROFILE_INCOMPLETE in stops

    def test_stop_means_no_recommendations_at_all(self) -> None:
        result = select(registry(supplement()), adult(pregnant=True))
        assert result.is_suspended
        assert result.recommended == ()
        assert not result.has_recommendations


class TestProductFiltering:
    def test_approved_and_filled_is_recommended(self) -> None:
        result = select(registry(supplement()), adult())
        assert [s.id for s in result.recommended] == ["demo"]

    def test_draft_is_never_recommended(self) -> None:
        result = select(registry(supplement(approved=False)), adult())
        assert result.recommended == ()
        assert result.excluded[0].reason is ExcludeReason.NOT_APPROVED

    def test_unfilled_dosage_is_never_recommended(self) -> None:
        """Бот не придумывает дозировки: нет записи — нет рекомендации."""
        result = select(registry(supplement(filled=False)), adult())
        assert result.recommended == ()
        assert result.excluded[0].reason is ExcludeReason.NOT_APPROVED

    def test_allergen_excludes_product(self) -> None:
        item = supplement(allergens=("Рыба",))
        result = select(registry(item), adult(allergies=("аллергия на рыбу",)))
        assert result.recommended == ()
        assert result.excluded[0].reason is ExcludeReason.ALLERGEN

    def test_contraindication_matches_condition(self) -> None:
        item = supplement(contraindications=("Заболевания почек",))
        result = select(registry(item), adult(conditions=("хроническая болезнь почек",)))
        assert result.recommended == ()
        assert result.excluded[0].reason is ExcludeReason.CONTRAINDICATION

    def test_min_age_above_user(self) -> None:
        item = supplement(min_age=21)
        result = select(registry(item), adult(age=19))
        assert result.recommended == ()
        assert result.excluded[0].reason is ExcludeReason.MIN_AGE

    def test_duplicate_component_is_excluded(self) -> None:
        """Нельзя удвоить один и тот же компонент из двух продуктов."""
        taken = supplement("taken", components=("Магний",))
        candidate = supplement("candidate", components=("Магний", "Витамин B6"))
        result = select(registry(candidate), adult(), already_taking=(taken,))
        assert result.recommended == ()
        assert result.excluded[0].reason is ExcludeReason.DUPLICATE_COMPONENT

    def test_already_taken_product_is_not_offered_again(self) -> None:
        item = supplement()
        result = select(registry(item), adult(), already_taking=(item,))
        assert result.recommended == ()
        assert result.excluded == ()

    def test_unrelated_allergy_does_not_exclude(self) -> None:
        item = supplement(allergens=("Рыба",))
        result = select(registry(item), adult(allergies=("пыльца",)))
        assert [s.id for s in result.recommended] == ["demo"]


class TestNoScenarioInput:
    def test_selection_does_not_depend_on_injury(self) -> None:
        """Подбор смотрит только на базу и анкету: диагностировать дефициты нельзя."""
        import inspect

        signature = inspect.signature(select)
        assert set(signature.parameters) == {
            "registry",
            "profile",
            "already_taking",
        }


class TestEmptyBase:
    def test_empty_registry_recommends_nothing(self) -> None:
        result = select(registry(), adult())
        assert result.recommended == ()
        assert not result.is_suspended
        assert not result.has_recommendations
