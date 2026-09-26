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
    """Базовая форма. Рабочая версия с enum создаётся `build_classify_model`."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(description="id сценария из списка или 'unknown'")
    confidence: float = Field(ge=0.0, le=1.0)
    body_part: str | None = Field(default=None, max_length=64)


class NormalizeAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str = Field(description="id варианта из списка или 'unclear'")


class ExplainStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1200)


@lru_cache(maxsize=32)
def build_classify_model(scenario_ids: tuple[str, ...]) -> type[ClassifyComplaint]:
    """Модель, где scenario_id — Literal из загруженных сценариев плюс 'unknown'.

    Валидация жёсткая: выдуманный id не пройдёт `model_validate` и уйдёт в фоллбэк.
    """
    allowed = Literal[(*scenario_ids, UNKNOWN)]  # type: ignore[valid-type]
    return create_model(
        "ClassifyComplaintStrict",
        __base__=ClassifyComplaint,
        scenario_id=(allowed, Field(description="id сценария из списка или 'unknown'")),
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
