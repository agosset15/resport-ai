"""Детерминированный подбор сценария по описанию словами.

Замечание куратора: бот не понимает травму, описанную своими словами. Таблица ниже —
формулировки, которыми пишут пользователи. От подбора требуется либо решить однозначно
(тогда модель не вызывается вовсе), либо поставить правильный сценарий на первое место
в сужённом списке — он и уходит в промпт и на кнопки.
"""

from __future__ import annotations

import pytest

from core.domain.enums import Sport
from core.scenarios.loader import load_registry
from core.scenarios.matching import common_tokens, prematch, stem, tokens
from tests.conftest import PROD_DEFS_DIR

#: описание -> ожидаемый ключ сценария (без префикса вида спорта)
EXACT_CASES = (
    ("вчера на игре подвернул голеностоп, сейчас опухло", "ankle_sprain"),
    ("подвернул ногу", "ankle_sprain"),
    ("наступил на чужую ногу и подвернул стопу", "ankle_sprain"),
    ("ушиб палец на тренировке", "finger_sprain"),
    ("выбил мизинец мячом", "finger_sprain"),
    ("палец распух и не сгибается", "finger_sprain"),
    ("потянул заднюю поверхность бедра на ускорении", "hamstring_strain"),
    ("колено болит при приседаниях и на лестнице", "patellofemoral_pain"),
)

#: Неоднозначные описания: точного ответа не ждём, но правильный сценарий обязан
#: быть в сужённом списке — иначе кнопки уводят пользователя не туда.
CANDIDATE_CASES = (
    ("болит в паху после удара по мячу", "adductor_strain"),
    ("забил бедро спереди", "quadriceps_strain"),
    ("больно приземляться, болит под чашечкой", "patellar_tendinopathy"),
    ("потянул пах на растяжке", "adductor_strain"),
)


@pytest.fixture(scope="module")
def prod():
    return load_registry(PROD_DEFS_DIR)


class TestStemmer:
    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("голеностопа", "голеностоп"),
            ("колене", "колен"),
            ("колено", "колен"),
            ("бедра", "бедр"),
            ("бедро", "бедр"),
            ("паху", "пах"),
            ("связки", "связк"),
        ],
    )
    def test_trims_endings(self, word: str, expected: str) -> None:
        assert stem(word) == expected

    def test_tokens_drop_short_words_and_punctuation(self) -> None:
        assert tokens("Вчера, на игре — подвернул ногу!") == {
            "вчер",
            "игр",
            "подвернул",
            "ног",
        }

    def test_yo_is_normalised(self) -> None:
        assert tokens("отёк") == tokens("отек")


class TestPrematch:
    @pytest.mark.parametrize(("complaint", "expected"), EXACT_CASES)
    def test_resolved_without_the_model(self, prod, complaint: str, expected: str) -> None:
        result = prematch(prod, complaint, Sport.FOOTBALL)
        assert result.is_exact, f"{complaint!r}: подбор не однозначен"
        assert result.exact is not None
        assert result.exact.id == f"football.{expected}"

    @pytest.mark.parametrize(("complaint", "expected"), CANDIDATE_CASES)
    def test_right_scenario_is_among_candidates(self, prod, complaint: str, expected: str) -> None:
        result = prematch(prod, complaint, Sport.FOOTBALL)
        ids = [s.id for s in result.candidates]
        assert f"football.{expected}" in ids, f"{complaint!r}: кандидаты {ids}"

    def test_candidate_list_is_narrower_than_the_full_set(self, prod) -> None:
        """Сужение — главная польза: 2–3 кнопки вместо семи «я тебя не понял»."""
        result = prematch(prod, "болит колено", Sport.FOOTBALL)
        assert 0 < len(result.candidates) < len(prod.for_sport(Sport.FOOTBALL))

    def test_empty_and_meaningless_input(self, prod) -> None:
        assert prematch(prod, "", Sport.FOOTBALL).candidates == ()
        assert not prematch(prod, "ой", Sport.FOOTBALL).is_exact

    def test_region_reported_for_exact_match(self, prod) -> None:
        result = prematch(prod, "подвернул голеностоп", Sport.FOOTBALL)
        assert result.region == "ankle_foot"

    def test_does_not_leak_across_sports(self, prod) -> None:
        result = prematch(prod, "подвернул голеностоп", Sport.BASKETBALL)
        assert result.exact is not None
        assert result.exact.sport is Sport.BASKETBALL


class TestCommonTokens:
    def test_frequent_words_are_ignored(self, prod) -> None:
        """Слова вроде «больно» есть почти везде и ничего не различают."""
        common = common_tokens(prod.for_sport(Sport.FOOTBALL))
        assert "больн" in common

    def test_discriminating_words_are_kept(self, prod) -> None:
        common = common_tokens(prod.for_sport(Sport.FOOTBALL))
        for token in ("голеностоп", "палец", "пах"):
            assert token not in common, token

    def test_single_scenario_has_nothing_in_common(self, prod) -> None:
        assert common_tokens([prod.require("football.ankle_sprain")]) == frozenset()
