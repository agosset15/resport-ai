from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities import Answer, Session
from core.domain.enums import SessionStatus, Sport
from infra.db.models import SessionAnswerModel, SessionModel
from infra.db.repositories.mappers import to_answer, to_session

ACTIVE_STATUSES = (SessionStatus.IN_PROGRESS, SessionStatus.PLAN_ACTIVE)


class SqlSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: UUID, sport: Sport) -> Session:
        model = SessionModel(user_id=user_id, sport=sport, status=SessionStatus.IN_PROGRESS)
        self._session.add(model)
        await self._session.flush()
        return to_session(model)

    async def get(self, session_id: UUID) -> Session | None:
        model = await self._session.get(SessionModel, session_id)
        return to_session(model) if model else None

    async def get_active(self, user_id: UUID) -> Session | None:
        model = await self._session.scalar(
            select(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.status.in_(ACTIVE_STATUSES))
            .order_by(SessionModel.created_at.desc())
            .limit(1)
        )
        return to_session(model) if model else None

    async def update(self, session: Session) -> None:
        await self._session.execute(
            update(SessionModel)
            .where(SessionModel.id == session.id)
            .values(
                sport=session.sport,
                scenario_id=session.scenario_id,
                scenario_version=session.scenario_version,
                status=session.status,
                complaint_text=session.complaint_text,
                finished_at=session.finished_at,
            )
        )

    async def abandon_active(self, user_id: UUID) -> None:
        await self._session.execute(
            update(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.status.in_(ACTIVE_STATUSES))
            .values(status=SessionStatus.ABANDONED, finished_at=datetime.now())
        )

    async def set_status(
        self, session_id: UUID, status: SessionStatus, finished_at: datetime | None = None
    ) -> None:
        await self._session.execute(
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(status=status, finished_at=finished_at)
        )

    async def upsert_answer(self, answer: Answer) -> None:
        stmt = pg_insert(SessionAnswerModel).values(
            session_id=answer.session_id,
            question_key=answer.question_key,
            option_id=answer.option_id,
            source=answer.source,
            raw_text=answer.raw_text,
        )
        await self._session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_answer_per_question",
                set_={
                    "option_id": stmt.excluded.option_id,
                    "source": stmt.excluded.source,
                    "raw_text": stmt.excluded.raw_text,
                },
            )
        )

    async def answers(self, session_id: UUID) -> Sequence[Answer]:
        models = await self._session.scalars(
            select(SessionAnswerModel)
            .where(SessionAnswerModel.session_id == session_id)
            .order_by(SessionAnswerModel.created_at)
        )
        return [to_answer(m) for m in models]

    async def answers_map(self, session_id: UUID) -> dict[str, str]:
        rows = await self._session.execute(
            select(SessionAnswerModel.question_key, SessionAnswerModel.option_id).where(
                SessionAnswerModel.session_id == session_id
            )
        )
        return {key: option for key, option in rows.all()}

    async def delete_answer(self, session_id: UUID, question_key: str) -> None:
        model = await self._session.scalar(
            select(SessionAnswerModel).where(
                SessionAnswerModel.session_id == session_id,
                SessionAnswerModel.question_key == question_key,
            )
        )
        if model is not None:
            await self._session.delete(model)
