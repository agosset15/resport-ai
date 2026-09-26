"""Задача 1: определить сценарий по свободному описанию проблемы.

При любом сомнении возвращаем None — бот покажет кнопочный выбор сценария.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from core.config import LlmSettings
from core.domain.enums import LlmTask, Sport
from core.domain.scenario import ScenarioRegistry
from core.llm.runner import LlmRunner
from core.llm.schemas import UNKNOWN, build_classify_model

SYSTEM = """Ты — вспомогательный классификатор в приложении для спортсменов.
Твоя задача: сопоставить жалобу спортсмена с одним из заранее заданных сценариев.

Правила:
- Выбирай только из предложенного списка id. Ничего не придумывай.
- Если жалоба не подходит ни под один сценарий или описание слишком общее — верни "unknown".
- confidence — честная оценка уверенности от 0 до 1.
- Ты не ставишь диагноз и не даёшь рекомендаций. Только классификация.
- Отвечай строго в заданной JSON-схеме."""


@dataclass(frozen=True, slots=True)
class Classification:
    scenario_id: str
    confidence: float
    body_part: str | None


def _user_prompt(complaint: str, sport: Sport, registry: ScenarioRegistry) -> str:
    lines = [f"Вид спорта: {sport.value}", "", "Доступные сценарии:"]
    for scenario in registry.for_sport(sport):
        hints = ", ".join(scenario.entry_hints)
        lines.append(f"- id: {scenario.id}")
        lines.append(f"  название: {scenario.title}")
        if scenario.summary:
            lines.append(f"  описание: {scenario.summary}")
        lines.append(f"  ключевые слова: {hints}")
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
) -> Classification | None:
    """None означает «не уверены» — вызывающий показывает кнопки."""
    candidates = registry.for_sport(sport)
    if not candidates:
        return None

    model_cls = build_classify_model(tuple(s.id for s in candidates))
    result = await runner.run(
        LlmTask.CLASSIFY_COMPLAINT,
        system=SYSTEM,
        user=_user_prompt(complaint, sport, registry),
        model_cls=model_cls,
        session_id=session_id,
    )
    if result is None:
        return None
    if result.scenario_id == UNKNOWN:
        return None
    if result.confidence < settings.classify_confidence_threshold:
        return None
    if registry.get(result.scenario_id) is None:
        return None

    return Classification(
        scenario_id=result.scenario_id,
        confidence=result.confidence,
        body_part=result.body_part,
    )
