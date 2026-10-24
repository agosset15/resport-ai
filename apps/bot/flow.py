"""Переходы опроса. Вынесено из хендлеров, чтобы шаг «вопрос → исход → план» был один."""

from __future__ import annotations

from uuid import UUID

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from apps.bot import texts
from apps.bot.keyboards.common import reminder_kb
from apps.bot.renderers import send_outcome, send_question, send_stage
from apps.bot.states import TrackerFlow, TriageFlow
from core.config import ContentSettings
from core.domain.entities import Session
from core.domain.enums import Outcome
from core.services.dto import QuestionView
from core.services.tracker import TrackerService
from core.services.triage import TriageService


async def advance(
    message: Message,
    state: FSMContext,
    *,
    triage: TriageService,
    tracker: TrackerService,
    content: ContentSettings,
    session_id: UUID,
    timezone: str | None = None,
) -> None:
    """Спрашивает следующий вопрос либо доводит сессию до исхода."""
    session = await triage.get_session(session_id)
    if session is None:
        await state.clear()
        await message.answer(texts.NO_ACTIVE_SESSION)
        return

    step = await triage.current_step(session)

    if isinstance(step, QuestionView):
        await state.set_state(TriageFlow.waiting_answer_text)
        await state.update_data(session_id=str(session.id), question_key=step.question.key)
        await send_question(message, step)
        return

    await send_outcome(message, step, content.specialist_url)

    if step.outcome is Outcome.REFER_SPECIALIST:
        await state.clear()
        return

    if step.plan_key is None:
        await state.clear()
        return

    if step.outcome is Outcome.SELF_REHAB:
        # План стартует только после явного согласия — handlers/triage.py::self_rehab_consent.
        await state.set_state(TriageFlow.waiting_self_rehab_consent)
        await state.update_data(session_id=str(session.id))
        return

    await start_plan(
        message,
        state,
        triage=triage,
        tracker=tracker,
        session=session,
        plan_key=step.plan_key,
        timezone=timezone,
    )


async def start_plan(
    message: Message,
    state: FSMContext,
    *,
    triage: TriageService,
    tracker: TrackerService,
    session: Session,
    plan_key: str,
    timezone: str | None = None,
) -> None:
    """Выдаёт план и запускает трекер. Общий хвост для recovery_plan и self_rehab."""
    scenario = triage.scenario_of(session)
    plan, _ = await tracker.start_plan(session, scenario, plan_key)
    stage = await tracker.today_view(plan, timezone=timezone)
    total_days = sum(s.days for s in tracker.plan_of(plan).stages)

    await message.answer(texts.PLAN_STARTED.format(days=total_days))
    await send_stage(message, stage)

    await state.set_state(TrackerFlow.waiting_reminder_time)
    await state.update_data(plan_id=str(plan.id))
    await message.answer(texts.ASK_REMINDER_TIME, reply_markup=reminder_kb())
