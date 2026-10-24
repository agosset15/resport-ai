"""Опрос: ответы кнопкой и свободным текстом."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from apps.bot.flow import advance, start_plan
from apps.bot.keyboards.common import (
    AnswerCB,
    SelfRehabCB,
    options_kb,
    specialist_kb,
)
from apps.bot.states import TriageFlow
from core.config import ContentSettings
from core.domain.enums import EventType
from core.services.tracker import TrackerService
from core.services.triage import TriageService
from core.services.user import UserService

router = Router(name="triage")


@router.callback_query(AnswerCB.filter())
@inject
async def answer_button(
    callback: CallbackQuery,
    callback_data: AnswerCB,
    state: FSMContext,
    users: FromDishka[UserService],
    triage: FromDishka[TriageService],
    tracker: FromDishka[TrackerService],
    content: FromDishka[ContentSettings],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return

    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    session = await triage.active_session(user)
    if session is None or session.scenario_id is None:
        await callback.answer(texts.NO_ACTIVE_SESSION, show_alert=True)
        return

    result = await triage.answer_with_option(
        session, callback_data.question_key, callback_data.option_id
    )
    if not result.accepted:
        await callback.answer("Вариант больше не актуален", show_alert=True)
        return

    await callback.message.edit_reply_markup(reply_markup=None)
    await advance(
        callback.message,
        state,
        triage=triage,
        tracker=tracker,
        content=content,
        session_id=session.id,
        timezone=user.timezone,
    )
    await callback.answer()


@router.message(TriageFlow.waiting_answer_text, F.text)
@inject
async def answer_text(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    triage: FromDishka[TriageService],
    tracker: FromDishka[TrackerService],
    content: FromDishka[ContentSettings],
) -> None:
    """Свободный текст нормализует LLM. Не распозналось — переспрашиваем кнопками."""
    if message.from_user is None or message.text is None:
        return

    data = await state.get_data()
    question_key = data.get("question_key")
    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    session = await triage.active_session(user)
    if session is None or session.scenario_id is None or question_key is None:
        await message.answer(texts.NO_ACTIVE_SESSION)
        await state.clear()
        return

    scenario = triage.scenario_of(session)
    question = scenario.question(question_key)
    if question is None:
        await message.answer(texts.NO_ACTIVE_SESSION)
        await state.clear()
        return

    result = await triage.answer_with_text(session, question, message.text)
    if not result.accepted:
        await message.answer(
            texts.ANSWER_NOT_UNDERSTOOD,
            reply_markup=options_kb(question.key, question.options),
        )
        return

    await advance(
        message,
        state,
        triage=triage,
        tracker=tracker,
        content=content,
        session_id=session.id,
        timezone=user.timezone,
    )


@router.callback_query(TriageFlow.waiting_self_rehab_consent, SelfRehabCB.filter())
@inject
async def self_rehab_consent(
    callback: CallbackQuery,
    callback_data: SelfRehabCB,
    state: FSMContext,
    users: FromDishka[UserService],
    triage: FromDishka[TriageService],
    tracker: FromDishka[TrackerService],
    content: FromDishka[ContentSettings],
) -> None:
    """Без явного согласия план самостоятельного восстановления не стартует."""
    if callback.from_user is None or not isinstance(callback.message, Message):
        return

    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    session = await triage.active_session(user)
    if session is None or session.scenario_id is None:
        await callback.answer(texts.NO_ACTIVE_SESSION, show_alert=True)
        await state.clear()
        return

    await callback.message.edit_reply_markup(reply_markup=None)

    if not callback_data.accept:
        await triage.request_specialist(
            session,
            reason_code="user_declined_self_rehab",
            event=EventType.SELF_REHAB_DECLINED,
        )
        await state.clear()
        await callback.message.answer(
            texts.SELF_REHAB_DECLINED,
            reply_markup=specialist_kb(content.specialist_url),
        )
        await callback.answer()
        return

    # Решение движка детерминировано, поэтому план берём из него, а не из состояния FSM.
    decision = await triage.pending_decision(session)
    if decision is None or decision.plan_key is None:
        await callback.answer(texts.NO_ACTIVE_SESSION, show_alert=True)
        await state.clear()
        return

    await triage.confirm_self_rehab(session)
    await start_plan(
        callback.message,
        state,
        triage=triage,
        tracker=tracker,
        session=session,
        plan_key=decision.plan_key,
        timezone=user.timezone,
    )
    await callback.answer()
