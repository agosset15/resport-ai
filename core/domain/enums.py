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
    SELF_REHAB = "self_rehab"


class PlanStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ESCALATED = "escalated"
    DROPPED = "dropped"


class Feeling(StrEnum):
    BETTER = "better"
    SAME = "same"
    WORSE = "worse"


class PlanSource(StrEnum):
    """Откуда взялся план. Нагрузку из назначения бот не меняет сам."""

    SCENARIO = "scenario"
    PRESCRIPTION = "prescription"


class ItemKind(StrEnum):
    """Что отмечает пользователь в плане на сегодня."""

    EXERCISE = "exercise"
    TASK = "task"
    SUPPLEMENT = "supplement"


class ItemStatus(StrEnum):
    """Частичное выполнение считается отдельно и в зачёт программы не идёт."""

    DONE = "done"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class Swelling(StrEnum):
    NONE = "none"
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class DailyCapacity(StrEnum):
    """Что получается в быту — это и есть «повседневные возможности» из ТЗ."""

    FULL = "full"
    LIMITED = "limited"
    MINIMAL = "minimal"


class AnswerSource(StrEnum):
    BUTTON = "button"
    LLM = "llm"
    MANUAL = "manual"


class LlmTask(StrEnum):
    CLASSIFY_COMPLAINT = "classify_complaint"
    CLASSIFY_BODY_PART = "classify_body_part"
    PARSE_PRESCRIPTION = "parse_prescription"
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
    PRESCRIPTION_PARSED = "prescription_parsed"
    REMINDER_TIME_SET = "reminder_time_set"
    REMINDER_SENT = "reminder_sent"
    CHECKIN_SUBMITTED = "checkin_submitted"
    PLAN_ITEM_MARKED = "plan_item_marked"
    WELLBEING_LOGGED = "wellbeing_logged"
    PLAN_REVISED = "plan_revised"
    PROGRESS_VIEWED = "progress_viewed"
    REPORT_BUILT = "report_built"
    STAGE_ADVANCED = "stage_advanced"
    PLAN_ESCALATED = "plan_escalated"
    PLAN_COMPLETED = "plan_completed"
    SPECIALIST_CTA_CLICKED = "specialist_cta_clicked"
    SPECIALIST_REQUESTED = "specialist_requested"
    PAIN_POINT_CONFIRMED = "pain_point_confirmed"
    PAIN_POINT_REJECTED = "pain_point_rejected"
    SELF_REHAB_OFFERED = "self_rehab_offered"
    SELF_REHAB_STARTED = "self_rehab_started"
    SELF_REHAB_DECLINED = "self_rehab_declined"
