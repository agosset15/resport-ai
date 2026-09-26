"""Перечисления домена. Значения совпадают с native enum-типами PostgreSQL."""

from enum import StrEnum


class Sport(StrEnum):
    FOOTBALL = "football"
    BASKETBALL = "basketball"


class SessionStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    REFERRED = "referred"
    PLAN_ACTIVE = "plan_active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class Outcome(StrEnum):
    REFER_SPECIALIST = "refer_specialist"
    RECOVERY_PLAN = "recovery_plan"


class PlanStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    DROPPED = "dropped"


class Feeling(StrEnum):
    BETTER = "better"
    SAME = "same"
    WORSE = "worse"


class AnswerSource(StrEnum):
    BUTTON = "button"
    LLM = "llm"
    MANUAL = "manual"


class LlmTask(StrEnum):
    CLASSIFY_COMPLAINT = "classify_complaint"
    NORMALIZE_ANSWER = "normalize_answer"
    EXPLAIN_STEP = "explain_step"


class EventType(StrEnum):
    """Типы событий для воронки в Metabase."""

    BOT_STARTED = "bot_started"
    CONSENT_GIVEN = "consent_given"
    SPORT_SELECTED = "sport_selected"
    COMPLAINT_SUBMITTED = "complaint_submitted"
    SCENARIO_CLASSIFIED = "scenario_classified"
    SCENARIO_FALLBACK = "scenario_fallback"
    QUESTION_ANSWERED = "question_answered"
    RED_FLAG_TRIGGERED = "red_flag_triggered"
    TRIAGE_COMPLETED = "triage_completed"
    PLAN_STARTED = "plan_started"
    REMINDER_TIME_SET = "reminder_time_set"
    REMINDER_SENT = "reminder_sent"
    CHECKIN_SUBMITTED = "checkin_submitted"
    STAGE_ADVANCED = "stage_advanced"
    PLAN_ESCALATED = "plan_escalated"
    PLAN_COMPLETED = "plan_completed"
    SPECIALIST_CTA_CLICKED = "specialist_cta_clicked"
