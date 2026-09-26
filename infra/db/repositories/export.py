"""Плоские выборки для админ-выгрузки (CSV). Панели в MVP нет — по ТЗ и не нужно."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infra.db.models import (
    CheckinModel,
    RecoveryPlanModel,
    SessionAnswerModel,
    SessionModel,
    TriageResultModel,
    UserModel,
)


class SqlExportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sessions(self) -> list[dict[str, Any]]:
        # question=option(source) через ; — источник ответа нужен для разбора спорных случаев
        answer_line = (
            SessionAnswerModel.question_key
            + "="
            + SessionAnswerModel.option_id
            + "("
            + cast(SessionAnswerModel.source, Text)
            + ")"
        )
        answers = (
            select(
                SessionAnswerModel.session_id.label("sid"),
                func.string_agg(answer_line, "; ").label("answers"),
            )
            .group_by(SessionAnswerModel.session_id)
            .subquery()
        )
        rows = await self._session.execute(
            select(
                SessionModel.id,
                UserModel.tg_id,
                UserModel.username,
                SessionModel.sport,
                SessionModel.scenario_id,
                SessionModel.scenario_version,
                SessionModel.status,
                SessionModel.complaint_text,
                TriageResultModel.outcome,
                TriageResultModel.reason_codes,
                TriageResultModel.triggered_flags,
                answers.c.answers,
                SessionModel.created_at,
                SessionModel.finished_at,
            )
            .join(UserModel, UserModel.id == SessionModel.user_id)
            .outerjoin(TriageResultModel, TriageResultModel.session_id == SessionModel.id)
            .outerjoin(answers, answers.c.sid == SessionModel.id)
            .order_by(SessionModel.created_at)
        )
        return [dict(row) for row in rows.mappings()]

    async def checkins(self) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            select(
                CheckinModel.id,
                CheckinModel.plan_id,
                RecoveryPlanModel.session_id,
                UserModel.tg_id,
                RecoveryPlanModel.plan_key,
                RecoveryPlanModel.status,
                CheckinModel.stage_index,
                CheckinModel.date,
                CheckinModel.feeling,
                CheckinModel.tasks_done,
                CheckinModel.note,
                CheckinModel.created_at,
            )
            .join(RecoveryPlanModel, RecoveryPlanModel.id == CheckinModel.plan_id)
            .join(SessionModel, SessionModel.id == RecoveryPlanModel.session_id)
            .join(UserModel, UserModel.id == SessionModel.user_id)
            .order_by(CheckinModel.date)
        )
        return [dict(row) for row in rows.mappings()]

    async def funnel(self) -> list[dict[str, Any]]:
        rows = await self._session.execute(
            select(SessionModel.status, func.count()).group_by(SessionModel.status)
        )
        return [{"status": status.value, "count": count} for status, count in rows.all()]
