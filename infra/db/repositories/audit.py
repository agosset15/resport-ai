"""Аудит LLM-вызовов и продуктовые события."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.enums import EventType, LlmTask
from infra.db.models import EventModel, LlmCallModel


class SqlLlmCallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        task: LlmTask,
        model: str,
        session_id: UUID | None = None,
        prompt_hash: str | None = None,
        request: dict[str, Any] | None = None,
        response: dict[str, Any] | None = None,
        valid: bool = False,
        error: str | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        latency_ms: int | None = None,
    ) -> None:
        self._session.add(
            LlmCallModel(
                task=task,
                model=model,
                session_id=session_id,
                prompt_hash=prompt_hash,
                request=request,
                response=response,
                valid=valid,
                error=error,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
        )


class SqlEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        event_type: EventType,
        *,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            EventModel(
                type=event_type.value,
                user_id=user_id,
                session_id=session_id,
                payload=payload or {},
            )
        )
