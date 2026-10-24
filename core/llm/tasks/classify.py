"""Задача 1: определить сценарий по свободному описанию проблемы.

При любом сомнении возвращаем None — бот покажет кнопочный выбор сценария.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from core.config import LlmSettings
from core.domain.enums import LlmTask, Sport
from core.domain.scenario import Scenario, ScenarioRegistry
from core.llm.runner import LlmRunner
from core.llm.schemas import UNKNOWN, build_classify_model

SYSTEM = """Ты — вспомогательный классификатор в приложении для спортсменов.
Твоя задача: сопоставить жалобу спортсмена с одним из заранее заданных сценариев.

Порядок работы:
1. Сначала определи область тела (body_region) — только из предложенных.
2. Затем выбери сценарий среди сценариев этой области.

Правила:
- Выбирай только из предложенного списка id. Ничего не придумывай.
- Бытовой язык — норма. Отсутствие медицинских терминов не повод возвращать "unknown":
  «подвернул ногу», «забил бедро», «выбил палец» — это достаточные описания.
- Если подходят два сценария — выбери более частый, второй укажи в alternatives,
  а confidence не ставь выше 0.6.
- "unknown" возвращай, только если описание не указывает даже на область тела.
- confidence — честная оценка уверенности от 0 до 1.
- Ты не ставишь диагноз и не даёшь рекомендаций. Только классификация.
- Отвечай строго в заданной JSON-схеме."""


@dataclass(frozen=True, slots=True)
class Classification:
    scenario_id: str
    confidence: float
    body_part: str | None
    body_region: str | None = None
    alternatives: tuple[str, ...] = ()
    #: Уверенности хватило, чтобы сразу идти в опрос, а не предлагать выбор.
    accepted: bool = True


def _user_prompt(complaint: str, sport: Sport, candidates: Sequence[Scenario]) -> str:
    """Кандидаты сгруппированы по области тела: так модель сначала выбирает место."""
    lines = [f"Вид спорта: {sport.value}", "", "Доступные сценарии по областям тела:"]
    by_region: dict[str, list[Scenario]] = {}
    for scenario in candidates:
        by_region.setdefault(scenario.body_region or UNKNOWN, []).append(scenario)

    for region, scenarios in by_region.items():
        lines.append(f"\nобласть {region}:")
        for scenario in scenarios:
            lines.append(f"- id: {scenario.id}")
            lines.append(f"  название: {scenario.title}")
            if scenario.summary:
                lines.append(f"  описание: {scenario.summary}")
            lines.append(f"  ключевые слова: {', '.join(scenario.entry_hints)}")
    lines += ["", "Жалоба спортсмена:", complaint.strip()]
    return "\n".join(lines)


async def classify_complaint(
    runner: LlmRunner,
    settings: LlmSettings,
    registry: ScenarioRegistry,
    *,
    complaint: str,
    sport: Sport,
    session_id: UUID | None = None,
    candidates: Sequence[Scenario] = (),
) -> Classification | None:
    """None означает «совсем не уверены» — вызывающий показывает кнопки.

    `candidates` — сужённый детерминированным предматчем список. Чем короче список,
    тем меньше модель размазывает уверенность между почти синонимами.
    """
    pool = tuple(candidates) or registry.for_sport(sport)
    if not pool:
        return None

    regions = tuple(sorted({s.body_region for s in pool if s.body_region}))
    model_cls = build_classify_model(tuple(s.id for s in pool), regions)
    result = await runner.run(
        LlmTask.CLASSIFY_COMPLAINT,
        system=SYSTEM,
        user=_user_prompt(complaint, sport, pool),
        model_cls=model_cls,
        session_id=session_id,
    )
    if result is None or result.scenario_id == UNKNOWN:
        return None

    scenario = registry.get(result.scenario_id)
    if scenario is None:
        return None

    # Несогласованность «область тела vs сценарий» — признак уверенной ошибки.
    if (
        result.body_region != UNKNOWN
        and scenario.body_region is not None
        and result.body_region != scenario.body_region
    ):
        return None

    if result.confidence < settings.classify_suggest_threshold:
        return None

    return Classification(
        scenario_id=result.scenario_id,
        confidence=result.confidence,
        body_part=result.body_part,
        body_region=result.body_region if result.body_region != UNKNOWN else None,
        alternatives=tuple(a for a in result.alternatives if a != result.scenario_id),
        accepted=result.confidence >= settings.classify_confidence_threshold,
    )
