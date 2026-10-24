"""Pydantic-схемы ответов LLM.

Ключевое: `scenario_id` и `option_id` — enum, собранный из загруженных YAML. Модель физически
не может вернуть несуществующий сценарий или вариант ответа: такой ответ не пройдёт валидацию
и превратится в фоллбэк на кнопки.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

UNKNOWN = "unknown"
UNCLEAR = "unclear"


class ClassifyComplaint(BaseModel):
    """Базовая форма. Рабочая версия с enum создаётся `build_classify_model`.

    Порядок полей значим: модель генерирует их по очереди, поэтому `body_region`
    объявлен первым — сначала определяется область тела, и уже внутри неё
    выбирается сценарий. Сужение получается бесплатно, без второго запроса.
    """

    model_config = ConfigDict(extra="forbid")

    # Значение по умолчанию: провайдер без structured output или старый ответ из
    # кэша не должны ронять разбор — несогласованность ловится уровнем выше.
    body_region: str = Field(default=UNKNOWN, description="область тела из списка или 'unknown'")
    scenario_id: str = Field(description="id сценария из списка или 'unknown'")
    confidence: float = Field(ge=0.0, le=1.0)
    body_part: str | None = Field(default=None, max_length=64)
    alternatives: list[str] = Field(
        default_factory=list,
        max_length=2,
        description="до двух других подходящих id, если выбор неочевиден",
    )


class NormalizeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str = Field(description="id варианта из списка или 'unclear'")


class ExplainStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1200)


@lru_cache(maxsize=32)
def build_classify_model(
    scenario_ids: tuple[str, ...], regions: tuple[str, ...] = ()
) -> type[ClassifyComplaint]:
    """Модель, где scenario_id и body_region — Literal из загруженных сценариев.

    Валидация жёсткая: выдуманный id не пройдёт `model_validate` и уйдёт в фоллбэк.
    """
    allowed = Literal[(*scenario_ids, UNKNOWN)]  # type: ignore[valid-type]
    allowed_regions = Literal[(*regions, UNKNOWN)] if regions else str
    return create_model(
        "ClassifyComplaintStrict",
        __base__=ClassifyComplaint,
        body_region=(
            allowed_regions,
            Field(default=UNKNOWN, description="область тела из списка или 'unknown'"),
        ),
        scenario_id=(allowed, Field(description="id сценария из списка или 'unknown'")),
        alternatives=(
            list[allowed],
            Field(default_factory=list, max_length=2),
        ),
    )


@lru_cache(maxsize=256)
def build_normalize_model(option_ids: tuple[str, ...]) -> type[NormalizeAnswer]:
    allowed = Literal[(*option_ids, UNCLEAR)]  # type: ignore[valid-type]
    return create_model(
        "NormalizeAnswerStrict",
        __base__=NormalizeAnswer,
        option_id=(allowed, Field(description="id варианта из списка или 'unclear'")),
    )


def json_schema_of(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema для structured output провайдера."""
    schema = model.model_json_schema()
    schema.pop("title", None)
    schema["additionalProperties"] = False
    return schema
