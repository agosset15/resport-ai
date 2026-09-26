"""ORM-модель -> сущность домена. Обратное преобразование делают сами репозитории."""

from __future__ import annotations

from core.domain.entities import (
    Answer,
    Checkin,
    RecoveryPlan,
    Session,
    TriageResult,
    User,
)
from infra.db.models import (
    CheckinModel,
    RecoveryPlanModel,
    SessionAnswerModel,
    SessionModel,
    TriageResultModel,
    UserModel,
)


def to_user(model: UserModel) -> User:
    return User(
        id=model.id,
        tg_id=model.tg_id,
        username=model.username,
        locale=model.locale,
        consent_version=model.consent_version,
        consent_at=model.consent_at,
        reminder_time=model.reminder_time,
        timezone=model.timezone,
        created_at=model.created_at,
    )


def to_session(model: SessionModel) -> Session:
    return Session(
        id=model.id,
        user_id=model.user_id,
        sport=model.sport,
        status=model.status,
        scenario_id=model.scenario_id,
        scenario_version=model.scenario_version,
        complaint_text=model.complaint_text,
        created_at=model.created_at,
        finished_at=model.finished_at,
    )


def to_answer(model: SessionAnswerModel) -> Answer:
    return Answer(
        id=model.id,
        session_id=model.session_id,
        question_key=model.question_key,
        option_id=model.option_id,
        source=model.source,
        raw_text=model.raw_text,
        created_at=model.created_at,
    )


def to_triage(model: TriageResultModel) -> TriageResult:
    return TriageResult(
        id=model.id,
        session_id=model.session_id,
        outcome=model.outcome,
        reason_codes=list(model.reason_codes or []),
        triggered_flags=list(model.triggered_flags or []),
        explanation_text=model.explanation_text,
        created_at=model.created_at,
    )


def to_plan(model: RecoveryPlanModel) -> RecoveryPlan:
    return RecoveryPlan(
        id=model.id,
        session_id=model.session_id,
        plan_key=model.plan_key,
        plan_snapshot=dict(model.plan_snapshot or {}),
        current_stage=model.current_stage,
        status=model.status,
        stage_started_at=model.stage_started_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
    )


def to_checkin(model: CheckinModel) -> Checkin:
    return Checkin(
        id=model.id,
        plan_id=model.plan_id,
        date=model.date,
        stage_index=model.stage_index,
        feeling=model.feeling,
        tasks_done=list(model.tasks_done or []),
        note=model.note,
        created_at=model.created_at,
    )
