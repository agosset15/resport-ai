"""Исполнитель LLM-задач: ретраи, таймаут, кэш, аудит, строгая валидация.

Любой сбой — это не исключение наружу, а `None`. Вызывающий код обязан иметь фоллбэк
на кнопки или статичный текст: бот не имеет права молчать из-за недоступной модели.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ValidationError

from core.config import LlmSettings
from core.domain.enums import LlmTask
from core.llm.provider import LlmProvider, LlmResult, LlmUnavailable
from core.llm.schemas import json_schema_of
from core.services.protocols import LlmCallRepository
from infra.telemetry import get_logger

T = TypeVar("T", bound=BaseModel)
log = get_logger("llm.runner")


class LlmCache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class NullCache:
    async def get(self, key: str) -> str | None:
        return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        return None


def prompt_hash(task: LlmTask, system: str, user: str, model: str) -> str:
    payload = f"{task.value}|{model}|{system}|{user}".encode()
    return hashlib.sha256(payload).hexdigest()


class LlmRunner:
    def __init__(
        self,
        provider: LlmProvider,
        settings: LlmSettings,
        audit: LlmCallRepository,
        cache: LlmCache | None = None,
    ) -> None:
        self._provider = provider
        self._settings = settings
        self._audit = audit
        self._cache = cache or NullCache()

    def is_enabled(self, task: LlmTask) -> bool:
        return task.value in self._settings.enabled_tasks and self._provider.name != "null"

    async def run(
        self,
        task: LlmTask,
        *,
        system: str,
        user: str,
        model_cls: type[T],
        session_id: UUID | None = None,
        use_cache: bool = True,
    ) -> T | None:
        """Возвращает валидный объект или None. None = включай фоллбэк."""
        if not self.is_enabled(task):
            return None

        key = prompt_hash(task, system, user, self._provider.model)

        if use_cache:
            cached = await self._safe_cache_get(key)
            if cached is not None:
                try:
                    return model_cls.model_validate_json(cached)
                except ValidationError:
                    log.warning("llm.cache_invalid", task=task.value)

        started = time.monotonic()
        result: LlmResult | None = None
        error: str | None = None

        for attempt in range(self._settings.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    self._provider.complete(
                        system=system,
                        user=user,
                        schema=json_schema_of(model_cls),
                        max_tokens=self._settings.max_output_tokens,
                    ),
                    timeout=self._settings.timeout_seconds,
                )
                break
            except (TimeoutError, LlmUnavailable) as exc:
                error = f"{type(exc).__name__}: {exc}"
                log.warning("llm.retry", task=task.value, attempt=attempt, error=error)
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                log.error("llm.failed", task=task.value, error=error)
                break

        latency_ms = int((time.monotonic() - started) * 1000)

        if result is None:
            await self._record(
                task, session_id, key, system, user, None, False, error, None, latency_ms
            )
            return None

        parsed, parse_error = self._parse(result, model_cls)
        await self._record(
            task,
            session_id,
            key,
            system,
            user,
            result,
            parsed is not None,
            parse_error,
            result.data,
            result.latency_ms or latency_ms,
        )

        if parsed is None:
            log.warning("llm.invalid_output", task=task.value, error=parse_error)
            return None

        if use_cache:
            await self._safe_cache_set(key, parsed.model_dump_json())
        return parsed

    def _parse(self, result: LlmResult, model_cls: type[T]) -> tuple[T | None, str | None]:
        payload: Any = result.data
        if payload is None:
            try:
                payload = json.loads(_strip_fences(result.text))
            except json.JSONDecodeError as exc:
                return None, f"JSONDecodeError: {exc}"
        try:
            return model_cls.model_validate(payload), None
        except ValidationError as exc:
            return None, f"ValidationError: {exc.errors(include_url=False)}"

    async def _record(
        self,
        task: LlmTask,
        session_id: UUID | None,
        key: str,
        system: str,
        user: str,
        result: LlmResult | None,
        valid: bool,
        error: str | None,
        data: dict[str, Any] | None,
        latency_ms: int,
    ) -> None:
        try:
            await self._audit.add(
                task=task,
                model=self._provider.model,
                session_id=session_id,
                prompt_hash=key,
                request={"system": system, "user": user},
                response=data if data is not None else ({"text": result.text} if result else None),
                valid=valid,
                error=error,
                tokens_in=result.tokens_in if result else None,
                tokens_out=result.tokens_out if result else None,
                latency_ms=latency_ms,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("llm.audit_failed", task=task.value, error=str(exc))

    async def _safe_cache_get(self, key: str) -> str | None:
        try:
            return await self._cache.get(key)
        except Exception as exc:  # noqa: BLE001
            log.warning("llm.cache_unavailable", error=str(exc))
            return None

    async def _safe_cache_set(self, key: str, value: str) -> None:
        try:
            await self._cache.set(key, value, self._settings.cache_ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            log.warning("llm.cache_unavailable", error=str(exc))


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()
