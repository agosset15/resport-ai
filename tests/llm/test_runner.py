"""Ретраи LlmRunner: что повторяем, а что нет."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from core.config import LlmSettings
from core.domain.enums import LlmTask
from core.llm.provider import LlmRejected, LlmResult, LlmUnavailable
from core.llm.runner import LlmRunner
from core.llm.schemas import NormalizeAnswer
from tests.fakes import FakeLlmCallRepository


class CountingProvider:
    name = "counting"

    def __init__(self, error: Exception) -> None:
        self.model = "counting-1"
        self._error = error
        self.attempts = 0

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 700,
    ) -> LlmResult:
        self.attempts += 1
        raise self._error

    async def aclose(self) -> None:
        return None


def _runner(provider: CountingProvider) -> LlmRunner:
    settings = LlmSettings(
        provider="dslab",
        model="gpt-5.4-mini",
        api_key=SecretStr("k"),
        max_retries=2,
        enabled_tasks=["normalize_answer"],
    )
    return LlmRunner(provider, settings, FakeLlmCallRepository())


@pytest.mark.parametrize(
    ("error", "expected_attempts"),
    [
        (LlmUnavailable("5xx"), 3),  # max_retries=2 → 1 попытка + 2 повтора
        (LlmRejected("400: bad request"), 1),  # повтор даст тот же 400
    ],
)
async def test_retries_only_transient_failures(error: Exception, expected_attempts: int) -> None:
    provider = CountingProvider(error)
    runner = _runner(provider)

    result = await runner.run(
        LlmTask.NORMALIZE_ANSWER,
        system="s",
        user="u",
        model_cls=NormalizeAnswer,
        use_cache=False,
    )

    assert result is None  # фоллбэк на кнопки в любом случае
    assert provider.attempts == expected_attempts


async def test_rejection_is_recorded_in_audit() -> None:
    provider = CountingProvider(LlmRejected("400: no route"))
    audit = FakeLlmCallRepository()
    settings = LlmSettings(
        provider="dslab",
        model="gpt-5.4-mini",
        api_key=SecretStr("k"),
        enabled_tasks=["normalize_answer"],
    )

    await LlmRunner(provider, settings, audit).run(
        LlmTask.NORMALIZE_ANSWER,
        system="s",
        user="u",
        model_cls=NormalizeAnswer,
        use_cache=False,
    )

    assert len(audit.calls) == 1
    assert audit.calls[0]["valid"] is False
    assert "no route" in audit.calls[0]["error"]
