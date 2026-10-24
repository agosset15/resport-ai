"""HTTP-клиенты LLM-провайдеров. Реализуют core.llm.provider.LlmProvider."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from core.config import LlmSettings
from core.llm.provider import LlmProvider, LlmRejected, LlmResult, LlmUnavailable
from infra.telemetry import get_logger

TOOL_NAME = "respond"

log = get_logger("llm.clients")


class NullProvider:
    """Провайдер-заглушка: LLM выключена, бот работает на кнопках и статичных текстах."""

    name = "null"

    def __init__(self, model: str = "none") -> None:
        self.model = model

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 700,
    ) -> LlmResult:
        raise LlmUnavailable("LLM отключена (LLM_PROVIDER=null)")

    async def aclose(self) -> None:
        return None


class _HttpProvider:
    name = "http"

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 700,
    ) -> LlmResult:
        raise NotImplementedError

    def __init__(self, settings: LlmSettings, base_url: str, headers: dict[str, str]) -> None:
        self.model = settings.model
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(settings.timeout_seconds),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        started = time.monotonic()
        try:
            response = await self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise LlmUnavailable(f"HTTP-ошибка: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code >= 500 or response.status_code == 429:
            # Перегрузка или сбой на той стороне — повтор осмыслен.
            raise LlmUnavailable(f"{response.status_code}: {_error_detail(response)}")
        if response.status_code >= 400:
            # Запрос отвергнут: повтор тем же payload даст тот же 400.
            raise LlmRejected(f"{response.status_code}: {_error_detail(response)}")
        return response.json(), latency_ms


class AnthropicProvider(_HttpProvider):
    """Structured output через принудительный вызов инструмента."""

    name = "anthropic"

    def __init__(self, settings: LlmSettings) -> None:
        super().__init__(
            settings,
            base_url=settings.base_url or "https://api.anthropic.com",
            headers={
                "x-api-key": settings.api_key.get_secret_value(),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 700,
    ) -> LlmResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if schema is not None:
            payload["tools"] = [
                {
                    "name": TOOL_NAME,
                    "description": "Вернуть структурированный ответ",
                    "input_schema": schema,
                }
            ]
            payload["tool_choice"] = {"type": "tool", "name": TOOL_NAME}

        body, latency_ms = await self._post("/v1/messages", payload)
        usage = body.get("usage", {})
        data: dict[str, Any] | None = None
        text_parts: list[str] = []
        for block in body.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == TOOL_NAME:
                data = block.get("input")
            elif block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        return LlmResult(
            text="".join(text_parts),
            model=body.get("model", self.model),
            data=data,
            tokens_in=usage.get("input_tokens"),
            tokens_out=usage.get("output_tokens"),
            latency_ms=latency_ms,
        )


class OpenAiProvider(_HttpProvider):
    """Structured output через response_format=json_schema."""

    name = "openai"
    default_base_url = "https://api.openai.com"

    def __init__(self, settings: LlmSettings) -> None:
        super().__init__(
            settings,
            base_url=_strip_v1(settings.base_url or self.default_base_url),
            headers={
                "Authorization": f"Bearer {settings.api_key.get_secret_value()}",
                "content-type": "application/json",
            },
        )

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 700,
    ) -> LlmResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_completion_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": TOOL_NAME, "schema": schema, "strict": True},
            }

        body, latency_ms = await self._post("/v1/chat/completions", payload)
        usage = body.get("usage", {})
        choices = body.get("choices") or []
        text = choices[0]["message"]["content"] if choices else ""
        data = _try_json(text)

        return LlmResult(
            text=text or "",
            model=body.get("model", self.model),
            data=data,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )


class DsLabProvider(OpenAiProvider):
    """DSLab (https://api.dslab.tech/v1) — OpenAI-совместимый шлюз к сторонним моделям.

    Отличается от OpenAI базовым URL и тем, что часть моделей не принимает
    strict-режим json_schema, поэтому payload упрощаем. Лимит вывода называется
    по-разному: старые chat-модели ждут `max_tokens`, reasoning-маршруты OpenAI
    (gpt-5, o1/o3/o4) — `max_completion_tokens`. См. `_token_field`.
    """

    name = "dslab"
    default_base_url = "https://api.dslab.tech"

    def __init__(self, settings: LlmSettings) -> None:
        super().__init__(settings)
        # Определяются по имени модели, уточняются по ответам шлюза (см. complete).
        self._token_field = _token_field(settings.model)
        self._response_format_supported = True

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 700,
    ) -> LlmResult:
        """Запрос с деградацией под маршрут, который шлюз выбрал для модели.

        Шлюз молча меняет апстрим и отвечает 400 вида «no other route for this model
        would accept it», не называя поле. Поэтому по очереди снимаем то, что маршруты
        принимают по-разному: имя лимита вывода, затем `response_format`. Выбор
        запоминается на процесс, чтобы не платить лишним запросом на каждый вызов.
        """
        body: dict[str, Any] | None = None
        latency_ms = 0
        last_error: LlmRejected | None = None

        for _ in range(3):
            try:
                body, latency_ms = await self._post(
                    "/v1/chat/completions",
                    self._payload(system, user, schema, max_tokens),
                )
                break
            except LlmRejected as exc:
                last_error = exc
                if not self._degrade(str(exc), has_schema=schema is not None):
                    raise
        if body is None:
            raise last_error if last_error is not None else LlmRejected("Шлюз отверг все варианты")

        usage = body.get("usage", {})
        choices = body.get("choices") or []
        text = choices[0]["message"].get("content") if choices else ""
        data = _try_json(text)

        return LlmResult(
            text=text or "",
            model=body.get("model", self.model),
            data=data,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )

    def _payload(
        self, system: str, user: str, schema: dict[str, Any] | None, max_tokens: int
    ) -> dict[str, Any]:
        system_prompt = system
        if schema is not None and not self._response_format_supported:
            system_prompt = _schema_in_prompt(system, schema)
        payload: dict[str, Any] = {
            "model": self.model,
            self._token_field: max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user},
            ],
        }
        if schema is not None and self._response_format_supported:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": TOOL_NAME, "schema": schema},
            }
        return payload

    def _degrade(self, error: str, *, has_schema: bool) -> bool:
        """Снимает следующую несовместимость. False — снимать больше нечего."""
        if _is_token_field_rejection(error, self._token_field):
            self._token_field = _other_token_field(self._token_field)
            log.warning("llm.dslab_token_field_switched", model=self.model, field=self._token_field)
            return True
        if has_schema and self._response_format_supported:
            # Маршрут не умеет json_schema — просим JSON текстом, `_try_json` разберёт.
            self._response_format_supported = False
            log.warning("llm.dslab_response_format_dropped", model=self.model)
            return True
        return False


class GigaChatProvider(_HttpProvider):
    """OpenAI-совместимый API без structured output: схему передаём в system-промпте."""

    name = "gigachat"

    def __init__(self, settings: LlmSettings) -> None:
        super().__init__(
            settings,
            base_url=settings.base_url or "https://gigachat.devices.sberbank.ru/api/v1",
            headers={
                "Authorization": f"Bearer {settings.api_key.get_secret_value()}",
                "content-type": "application/json",
            },
        )

    async def complete(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        max_tokens: int = 700,
    ) -> LlmResult:
        system_prompt = system if schema is None else _schema_in_prompt(system, schema)
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user},
            ],
        }
        body, latency_ms = await self._post("/chat/completions", payload)
        usage = body.get("usage", {})
        choices = body.get("choices") or []
        text = choices[0]["message"]["content"] if choices else ""

        return LlmResult(
            text=text or "",
            model=body.get("model", self.model),
            data=_try_json(text),
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )


def _schema_in_prompt(system: str, schema: dict[str, Any]) -> str:
    """Схема в system-промпте — для маршрутов без structured output."""
    return (
        f"{system}\n\nОтветь одним JSON-объектом строго по схеме, без пояснений "
        f"и без markdown:\n{json.dumps(schema, ensure_ascii=False)}"
    )


def _error_detail(response: httpx.Response) -> str:
    """Читаемая причина ошибки.

    Раньше тело резалось до 200 символов, и `message`/`code` провайдера терялись —
    по логу нельзя было понять, какое поле не понравилось. Достаём поля явно.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text[:500]
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return json.dumps(body, ensure_ascii=False)[:500]
    parts = [str(error.get(field)) for field in ("message", "code", "param") if error.get(field)]
    detail = " | ".join(parts) or json.dumps(error, ensure_ascii=False)
    request_id = body.get("request_id") or error.get("request_id")
    if request_id:
        detail = f"{detail} (request_id={request_id})"
    return detail[:500]


#: Модели, чей маршрут у OpenAI принимает только `max_completion_tokens`.
_COMPLETION_TOKEN_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _token_field(model: str) -> str:
    """Как называется лимит вывода для этой модели."""
    name = model.lower().split("/")[-1]
    if name.startswith(_COMPLETION_TOKEN_PREFIXES):
        return "max_completion_tokens"
    return "max_tokens"


def _other_token_field(field: str) -> str:
    return "max_tokens" if field == "max_completion_tokens" else "max_completion_tokens"


def _is_token_field_rejection(message: str, sent_field: str) -> bool:
    """Отличает «не то имя лимита вывода» от прочих 400."""
    text = message.lower()
    if sent_field not in text:
        return False
    return _other_token_field(sent_field) in text or "unsupported" in text


def _strip_v1(base_url: str) -> str:
    """Провайдеры публикуют base_url то с `/v1`, то без; путь всегда добавляем сами."""
    trimmed = base_url.rstrip("/")
    return trimmed[: -len("/v1")] if trimmed.endswith("/v1") else trimmed


def _try_json(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def build_provider(settings: LlmSettings) -> LlmProvider:
    providers = {
        "anthropic": AnthropicProvider,
        "openai": OpenAiProvider,
        "dslab": DsLabProvider,
        "gigachat": GigaChatProvider,
    }
    factory = providers.get(settings.provider.lower())
    if factory is None or not settings.api_key.get_secret_value():
        return NullProvider(settings.model)
    return factory(settings)
