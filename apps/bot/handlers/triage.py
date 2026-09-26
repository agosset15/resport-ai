"""Опрос: ответы кнопкой и свободным текстом."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from apps.bot.flow import advance
from apps.bot.keyboards.common import AnswerCB, options_kb
from apps.bot.states import TriageFlow
from core.config import ContentSettings
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
