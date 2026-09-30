"""Тесты HTTP-клиентов LLM: сборка провайдера, URL и формат payload."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from core.config import LlmSettings
from infra.llm.clients import DsLabProvider, NullProvider, build_provider

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


def _settings(**overrides: Any) -> LlmSettings:
    defaults: dict[str, Any] = {
        "provider": "dslab",
        "model": "gpt-5.4-mini",
        "api_key": SecretStr("test-key"),
        "base_url": None,
    }
    return LlmSettings(**(defaults | overrides))


def _mock(provider: DsLabProvider, captured: dict[str, Any], body: dict[str, Any]) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=body)

    provider._client = httpx.AsyncClient(
        base_url=provider._client.base_url,
        headers=provider._client.headers,
        transport=httpx.MockTransport(handler),
    )


def test_build_provider_returns_dslab() -> None:
    provider = build_provider(_settings())
    assert isinstance(provider, DsLabProvider)
    assert provider.name == "dslab"


def test_build_provider_falls_back_to_null_without_key() -> None:
    assert isinstance(build_provider(_settings(api_key=SecretStr(""))), NullProvider)


@pytest.mark.parametrize("base_url", [None, "https://api.dslab.tech/v1", "https://api.dslab.tech/"])
def test_base_url_variants_hit_the_same_endpoint(base_url: str | None) -> None:
    provider = DsLabProvider(_settings(base_url=base_url))
    captured: dict[str, Any] = {}
    _mock(
        provider,
        captured,
        {
            "model": "gpt-5.4-mini",
            "choices": [{"message": {"content": "привет"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 3},
        },
    )

    import asyncio

    result = asyncio.run(provider.complete(system="s", user="u"))

    assert captured["url"] == "https://api.dslab.tech/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["payload"]["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]
    assert captured["payload"]["max_tokens"] == 700
    assert result.text == "привет"
    assert result.tokens_in == 11
    assert result.tokens_out == 3
    assert result.latency_ms is not None


def test_schema_is_sent_as_json_schema_and_parsed() -> None:
    provider = DsLabProvider(_settings())
    captured: dict[str, Any] = {}
    _mock(
        provider,
        captured,
        {"choices": [{"message": {"content": '```json\n{"answer": "ок"}\n```'}}], "usage": {}},
    )

    import asyncio

    result = asyncio.run(provider.complete(system="s", user="u", schema=SCHEMA, max_tokens=64))

    assert captured["payload"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "respond", "schema": SCHEMA},
    }
    assert captured["payload"]["max_tokens"] == 64
    assert result.data == {"answer": "ок"}
