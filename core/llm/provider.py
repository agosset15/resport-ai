"""Порт LLM-провайдера.

Ни один сервис не знает, кто за этим стоит — OpenAI, Anthropic, GigaChat или заглушка.
Смена провайдера (в том числе на российский) не требует правок в core/services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class LlmUnavailable(Exception):
    """Провайдер не ответил: таймаут, сеть, 5xx, исчерпаны ретраи."""


class LlmInvalidOutput(Exception):
    """Ответ пришёл, но не разобрался в ожидаемую схему."""


@dataclass(frozen=True, slots=True)
class LlmResult:
    text: str
    model: str
    data: dict[str, Any] | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LlmProvider(Protocol):
    """Минимальный контракт. `schema` включает structured output, если провайдер его умеет."""

    name: str
    model: str

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 700,
    ) -> LlmResult: ...

    async def aclose(self) -> None: ...
