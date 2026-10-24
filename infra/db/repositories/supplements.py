"""Анкета, курсы приёма БАДов и нежелательные реакции.

Отметок приёма здесь нет: они идут в plan_item_logs с item_kind = 'supplement'.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.domain.entities import AdverseReaction, SupplementIntake, SupplementProfileRecord
from core.domain.enums import ReactionSeverity, SupplementStatus
from infra.db.models import (
    AdverseReactionModel,
    SupplementIntakeModel,
    SupplementProfileModel,
)
from infra.db.repositories.mappers import (
    to_adverse_reaction,
    to_supplement_intake,
    to_supplement_profile,
)


class SqlSupplementProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, user_id: UUID, answers: dict[str, Any]) -> None:
        statement = (
            insert(SupplementProfileModel)
            .values(user_id=user_id, answers=answers, updated_at=datetime.now(UTC))
            .on_conflict_do_update(
                index_elements=[SupplementProfileModel.user_id],
                set_={"answers": answers, "updated_at": datetime.now(UTC)},
            )
        )
        await self._session.execute(statement)

    async def get(self, user_id: UUID) -> SupplementProfileRecord | None:
        model = await self._session.scalar(
            select(SupplementProfileModel).where(SupplementProfileModel.user_id == user_id)
        )
        return to_supplement_profile(model) if model else None


class SqlSupplementIntakeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, intake: SupplementIntake) -> None:
        values = {
            "user_id": intake.user_id,
            "supplement_id": intake.supplement_id,
            "status": intake.status,
            "include_in_report": intake.include_in_report,
            "stopped_at": intake.stopped_at,
        }
        statement = (
            insert(SupplementIntakeModel)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_intake_per_supplement",
                set_={
                    "status": intake.status,
                    "include_in_report": intake.include_in_report,
                    "stopped_at": intake.stopped_at,
                },
            )
        )
        await self._session.execute(statement)

    async def set_status(self, user_id: UUID, supplement_id: str, status: SupplementStatus) -> None:
        stopped_at = datetime.now(UTC) if status is not SupplementStatus.ACTIVE else None
        await self.upsert(
            SupplementIntake(
                user_id=user_id,
                supplement_id=supplement_id,
                status=status,
                stopped_at=stopped_at,
            )
        )

    async def for_user(self, user_id: UUID) -> Sequence[SupplementIntake]:
        rows = await self._session.scalars(
            select(SupplementIntakeModel)
            .where(SupplementIntakeModel.user_id == user_id)
            .order_by(SupplementIntakeModel.started_at)
        )
        return [to_supplement_intake(row) for row in rows]

    async def active_for_user(self, user_id: UUID) -> Sequence[SupplementIntake]:
        rows = await self._session.scalars(
            select(SupplementIntakeModel).where(
                SupplementIntakeModel.user_id == user_id,
                SupplementIntakeModel.status == SupplementStatus.ACTIVE,
            )
        )
        return [to_supplement_intake(row) for row in rows]


class SqlAdverseReactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, user_id: UUID, supplement_id: str, severity: ReactionSeverity, text: str
    ) -> None:
        self._session.add(
            AdverseReactionModel(
                user_id=user_id, supplement_id=supplement_id, severity=severity, text=text
            )
        )
        await self._session.flush()

    async def for_user(self, user_id: UUID) -> Sequence[AdverseReaction]:
        rows = await self._session.scalars(
            select(AdverseReactionModel)
            .where(AdverseReactionModel.user_id == user_id)
            .order_by(AdverseReactionModel.created_at)
        )
        return [to_adverse_reaction(row) for row in rows]
