from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities import TriageResult
from infra.db.models import TriageResultModel
from infra.db.repositories.mappers import to_triage


class SqlTriageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, result: TriageResult) -> TriageResult:
        stmt = pg_insert(TriageResultModel).values(
            session_id=result.session_id,
            outcome=result.outcome,
            reason_codes=result.reason_codes,
            triggered_flags=result.triggered_flags,
            explanation_text=result.explanation_text,
        )
        upsert = stmt.on_conflict_do_update(
            index_elements=[TriageResultModel.session_id],
            set_={
                "outcome": stmt.excluded.outcome,
                "reason_codes": stmt.excluded.reason_codes,
                "triggered_flags": stmt.excluded.triggered_flags,
                "explanation_text": stmt.excluded.explanation_text,
            },
        ).returning(TriageResultModel)
        model: TriageResultModel = (await self._session.execute(upsert)).scalar_one()
        return to_triage(model)

    async def get(self, session_id: UUID) -> TriageResult | None:
        model = await self._session.scalar(
            select(TriageResultModel).where(TriageResultModel.session_id == session_id)
        )
        return to_triage(model) if model else None
