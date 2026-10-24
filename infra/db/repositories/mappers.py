"""ORM-модель -> сущность домена. Обратное преобразование делают сами репозитории."""

from __future__ import annotations

from core.domain.entities import (
    AdverseReaction,
    Answer,
    Checkin,
    PlanItemLog,
    PlanRevision,
    RecoveryPlan,
    Session,
    SupplementIntake,
    SupplementProfileRecord,
    TriageResult,
    User,
    WellbeingLog,
)
from infra.db.models import (
    AdverseReactionModel,
    CheckinModel,
    PlanItemLogModel,
    PlanRevisionModel,
    RecoveryPlanModel,
    SessionAnswerModel,
    SessionModel,
    SupplementIntakeModel,
    SupplementProfileModel,
    TriageResultModel,
    UserModel,
    WellbeingLogModel,
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
        source=model.source,
        version=model.version,
        status=model.status,
        stage_started_at=model.stage_started_at,
        started_at=model.started_at,
        finished_at=model.finished_at,
    )


def to_plan_item_log(model: PlanItemLogModel) -> PlanItemLog:
    return PlanItemLog(
        id=model.id,
        plan_id=model.plan_id,
        date=model.date,
        item_kind=model.item_kind,
        item_key=model.item_key,
        status=model.status,
        comment=model.comment,
        created_at=model.created_at,
    )


def to_wellbeing_log(model: WellbeingLogModel) -> WellbeingLog:
    return WellbeingLog(
        id=model.id,
        plan_id=model.plan_id,
        date=model.date,
        pain_0_10=model.pain_0_10,
        swelling=model.swelling,
        daily_capacity=model.daily_capacity,
        note=model.note,
        created_at=model.created_at,
    )


def to_plan_revision(model: PlanRevisionModel) -> PlanRevision:
    return PlanRevision(
        id=model.id,
        plan_id=model.plan_id,
        version=model.version,
        snapshot=dict(model.snapshot or {}),
        reason=model.reason,
        created_at=model.created_at,
    )


def to_supplement_profile(model: SupplementProfileModel) -> SupplementProfileRecord:
    return SupplementProfileRecord(
        id=model.id,
        user_id=model.user_id,
        answers=dict(model.answers or {}),
        updated_at=model.updated_at,
    )


def to_supplement_intake(model: SupplementIntakeModel) -> SupplementIntake:
    return SupplementIntake(
        id=model.id,
        user_id=model.user_id,
        supplement_id=model.supplement_id,
        status=model.status,
        include_in_report=model.include_in_report,
        started_at=model.started_at,
        stopped_at=model.stopped_at,
    )


def to_adverse_reaction(model: AdverseReactionModel) -> AdverseReaction:
    return AdverseReaction(
        id=model.id,
        user_id=model.user_id,
        supplement_id=model.supplement_id,
        severity=model.severity,
        text=model.text,
        created_at=model.created_at,
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
