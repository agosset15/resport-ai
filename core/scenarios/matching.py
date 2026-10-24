"""Детерминированный подбор сценария по свободному описанию травмы.

Зачем: куратор отметил, что бот плохо понимает описание словами. Три группы сценариев
пересекаются по формулировкам («болит колено» — и связка надколенника, и
пателлофеморальная боль), модель распределяла уверенность между почти синонимами и не
добиралась до порога, после чего пользователь получал список из семи кнопок.

Этот модуль — дешёвый путь до обращения к модели: если описание однозначно совпало с
подсказками одного сценария, LLM не нужна вовсе, а если нет — список кандидатов
сужается, и в промпт уходит не весь набор сценариев.

Чистая логика над данными: ни сети, ни I/O, ни зависимости от провайдера.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from core.domain.enums import Sport
from core.domain.scenario import Scenario, ScenarioRegistry

#: Минимальный вес, при котором подбор считается однозначным.
EXACT_MIN_SCORE = 2.0
#: Во сколько раз лидер должен опережать второго, чтобы обойтись без модели.
EXACT_MIN_RATIO = 2.0
#: Сколько сценариев отдаём в сужённый список.
MAX_CANDIDATES = 3

_WORD_RE = re.compile(r"[a-zа-я0-9]+")

#: Хвосты русских слов: грубый стеммер без внешних зависимостей.
#: «голеностопа» -> «голеностоп», «колене» -> «колен», «связки» -> «связк».
_SUFFIXES = (
    "ами",
    "ями",
    "ого",
    "его",
    "ому",
    "ему",
    "ыми",
    "ими",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ой",
    "ей",
    "ый",
    "ий",
    "ах",
    "ях",
    "ам",
    "ям",
    "ом",
    "ем",
    "ов",
    "ев",
    "ую",
    "юю",
    "а",
    "я",
    "ы",
    "и",
    "е",
    "о",
    "у",
    "ю",
    "ь",
)

_MIN_STEM = 3


@dataclass(frozen=True, slots=True)
class PrematchResult:
    """Что удалось понять без модели."""

    exact: Scenario | None
    candidates: tuple[Scenario, ...]
    region: str | None

    @property
    def is_exact(self) -> bool:
        return self.exact is not None


def stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM:
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> set[str]:
    """Нормализованные основы слов. Короткие слова отбрасываем: они ничего не различают."""
    lowered = text.casefold().replace("ё", "е")
    return {stem(w) for w in _WORD_RE.findall(lowered) if len(w) >= 3}


def _hint_score(hint_tokens: set[str], complaint_tokens: set[str], common: frozenset[str]) -> float:
    """Фраза целиком — вес 2, отдельное совпавшее слово — 0.5.

    Слова из `common` не считаются: «болит», «нога», «травма» встречаются почти в каждом
    сценарии и, если их учитывать, перетягивают подбор на случайного соседа.
    """
    if not hint_tokens:
        return 0.0
    if hint_tokens <= complaint_tokens:
        return 2.0
    overlap = (hint_tokens & complaint_tokens) - common
    return 0.5 * len(overlap)


def common_tokens(scenarios: Sequence[Scenario]) -> frozenset[str]:
    """Слова, встречающиеся в подсказках больше чем у половины сценариев."""
    if not scenarios:
        return frozenset()
    document_freq: dict[str, int] = {}
    for scenario in scenarios:
        seen: set[str] = set()
        for hint in (*scenario.entry_hints, scenario.title):
            seen |= tokens(hint)
        for token in seen:
            document_freq[token] = document_freq.get(token, 0) + 1
    threshold = max(2, len(scenarios) // 2)
    return frozenset(t for t, df in document_freq.items() if df > threshold)


def score_scenario(
    scenario: Scenario, complaint_tokens: set[str], common: frozenset[str] = frozenset()
) -> float:
    total = 0.0
    for hint in scenario.entry_hints:
        total += _hint_score(tokens(hint), complaint_tokens, common)
    total += _hint_score(tokens(scenario.title), complaint_tokens, common)
    return total


def prematch(registry: ScenarioRegistry, complaint: str, sport: Sport) -> PrematchResult:
    """Сценарий по описанию без обращения к модели.

    `exact` заполнен, только если лидер набрал достаточно и заметно опередил второго:
    при любом сомнении возвращаем сужённый список кандидатов, а решение остаётся за LLM
    или за кнопками.
    """
    complaint_tokens = tokens(complaint)
    if not complaint_tokens:
        return PrematchResult(exact=None, candidates=(), region=None)

    pool = registry.for_sport(sport)
    common = common_tokens(pool)
    scored = [(score_scenario(scenario, complaint_tokens, common), scenario) for scenario in pool]
    hits = sorted(
        ((score, scenario) for score, scenario in scored if score > 0),
        key=lambda pair: (-pair[0], pair[1].id),
    )
    if not hits:
        return PrematchResult(exact=None, candidates=(), region=None)

    best_score, best = hits[0]
    runner_up = hits[1][0] if len(hits) > 1 else 0.0
    candidates = tuple(scenario for _, scenario in hits[:MAX_CANDIDATES])

    # Область тела считаем общей, только если все кандидаты про одно место.
    regions = {s.body_region for s in candidates if s.body_region}
    region = regions.pop() if len(regions) == 1 else None

    is_exact = best_score >= EXACT_MIN_SCORE and best_score >= runner_up * EXACT_MIN_RATIO
    return PrematchResult(
        exact=best if is_exact else None,
        candidates=candidates,
        region=(region or best.body_region) if is_exact else region,
    )
