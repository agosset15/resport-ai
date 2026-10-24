"""Тесты HTTP-клиентов LLM: сборка провайдера, URL и формат payload."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from core.config import LlmSettings
from core.llm.provider import LlmRejected, LlmUnavailable
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

    result = asyncio.run(provider.complete(system="s", user="u"))

    assert captured["url"] == "https://api.dslab.tech/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer test-key"
    assert captured["payload"]["messages"] == [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
    ]
    assert captured["payload"]["max_completion_tokens"] == 700
    assert "max_tokens" not in captured["payload"]
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

    result = asyncio.run(provider.complete(system="s", user="u", schema=SCHEMA, max_tokens=64))

    assert captured["payload"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "respond", "schema": SCHEMA},
    }
    assert captured["payload"]["max_completion_tokens"] == 64
    assert result.data == {"answer": "ок"}


def test_chat_model_keeps_max_tokens() -> None:
    """Не-reasoning модели шлюза принимают только `max_tokens`."""
    provider = DsLabProvider(_settings(model="deepseek-chat"))
    captured: dict[str, Any] = {}
    _mock(provider, captured, {"choices": [{"message": {"content": "ок"}}], "usage": {}})

    asyncio.run(provider.complete(system="s", user="u"))

    assert captured["payload"]["max_tokens"] == 700
    assert "max_completion_tokens" not in captured["payload"]


def test_retries_with_other_token_field_when_gateway_rejects_it() -> None:
    """Шлюз переключил модель на другой маршрут: клиент меняет имя лимита и повторяет."""
    provider = DsLabProvider(_settings(model="deepseek-chat"))
    payloads: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        if "max_tokens" in payload:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "type": "invalid_request_error",
                        "message": (
                            "`max_tokens` is unsupported by the official OpenAI GPT-5 "
                            "reasoning route; use `max_completion_tokens`."
                        ),
                    }
                },
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "ок"}}], "usage": {}})

    provider._client = httpx.AsyncClient(
        base_url=provider._client.base_url,
        headers=provider._client.headers,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.complete(system="s", user="u"))

    assert result.text == "ок"
    assert [p for p in payloads if "max_completion_tokens" in p]
    assert len(payloads) == 2
    # Переключение запомнено: второй вызов сразу идёт с новым полем.
    asyncio.run(provider.complete(system="s", user="u"))
    assert "max_completion_tokens" in payloads[-1]
    assert len(payloads) == 3


def test_other_bad_request_is_not_retried() -> None:
    """400 не про имя лимита вывода — пробрасываем без повтора."""
    provider = DsLabProvider(_settings())
    calls: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "model not found"}})

    provider._client = httpx.AsyncClient(
        base_url=provider._client.base_url,
        headers=provider._client.headers,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LlmRejected):
        asyncio.run(provider.complete(system="s", user="u"))
    assert len(calls) == 1


def test_route_rejection_without_field_name_drops_response_format() -> None:
    """Шлюз отвергает запрос, не называя поле: снимаем response_format и повторяем."""
    provider = DsLabProvider(_settings())
    payloads: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        if "response_format" in payload:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "type": "invalid_request_error",
                        "message": (
                            "The request was rejected as invalid and no other route "
                            "for this model would accept it."
                        ),
                        "code": "no_route",
                    },
                    "request_id": "85b90e98",
                },
            )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"answer": "ок"}'}}], "usage": {}}
        )

    provider._client = httpx.AsyncClient(
        base_url=provider._client.base_url,
        headers=provider._client.headers,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.complete(system="s", user="u", schema=SCHEMA))

    assert result.data == {"answer": "ок"}
    assert len(payloads) == 2
    # Схема ушла в system-промпт, раз маршрут не принял response_format.
    assert "response_format" not in payloads[1]
    assert "answer" in payloads[1]["messages"][0]["content"]


def test_rejection_detail_keeps_provider_message_and_request_id() -> None:
    """Текст ошибки несёт message, code и request_id — иначе 400 не диагностируется."""
    provider = DsLabProvider(_settings())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {"message": "unsupported parameter: frequency_penalty", "code": "bad"},
                "request_id": "dc46389b",
            },
        )

    provider._client = httpx.AsyncClient(
        base_url=provider._client.base_url,
        headers=provider._client.headers,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LlmRejected) as excinfo:
        asyncio.run(provider.complete(system="s", user="u"))

    message = str(excinfo.value)
    assert "unsupported parameter: frequency_penalty" in message
    assert "dc46389b" in message
    assert message.startswith("400: ")


def test_server_error_stays_retryable() -> None:
    """5xx и 429 — не LlmRejected: их ретраить осмысленно."""
    provider = DsLabProvider(_settings())

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "overloaded"}})

    provider._client = httpx.AsyncClient(
        base_url=provider._client.base_url,
        headers=provider._client.headers,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LlmUnavailable) as excinfo:
        asyncio.run(provider.complete(system="s", user="u"))
    assert not isinstance(excinfo.value, LlmRejected)
