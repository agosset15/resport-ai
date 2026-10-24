"""Подтверждение точки боли по картинке и выбор дальнейшего пути.

Шаг стоит между классификацией и опросом: бот показывает картинку области, пользователь
подтверждает место, после чего выбирает запись к врачу или самостоятельную реабилитацию.

Важно: кнопка «Самостоятельная реабилитация» **открывает опрос, а не пропускает его**.
Красные флаги и правила «к врачу сегодня» по-прежнему перекрывают выбор пользователя —
иначе человек с деформацией и онемением получил бы упражнения по нажатию кнопки.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from apps.bot.flow import advance
from apps.bot.keyboards.common import (
    PainPointCB,
    RouteCB,
    route_kb,
    scenarios_kb,
    specialist_kb,
)
from apps.bot.states import TriageFlow
from core.config import ContentSettings
from core.domain.enums import EventType
from core.services.tracker import TrackerService
from core.services.triage import TriageService
from core.services.user import UserService

router = Router(name="pain_point")


@router.callback_query(TriageFlow.confirming_pain_point, PainPointCB.filter())
@inject
async def confirm_pain_point(
    callback: CallbackQuery,
    callback_data: PainPointCB,
    state: FSMContext,
    users: FromDishka[UserService],
    triage: FromDishka[TriageService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return

    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    session = await triage.active_session(user)
    if session is None:
        await callback.answer(texts.NO_ACTIVE_SESSION, show_alert=True)
        await state.clear()
        return

    await callback.message.edit_reply_markup(reply_markup=None)

    if callback_data.action == "reject":
        await triage.note_pain_point(session, confirmed=False)
        await state.set_state(TriageFlow.waiting_complaint)
        await callback.message.answer(
            texts.PAIN_POINT_REJECTED,
            reply_markup=scenarios_kb(triage.choices_for(session.sport)),
        )
        await callback.answer()
        return

    await triage.note_pain_point(session, confirmed=True)
    await state.set_state(TriageFlow.choosing_route)
    await callback.message.answer(texts.CHOOSE_ROUTE, reply_markup=route_kb())
    await callback.answer()


@router.callback_query(TriageFlow.choosing_route, RouteCB.filter())
@inject
async def choose_route(
    callback: CallbackQuery,
    callback_data: RouteCB,
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
        await state.clear()
        return

    await callback.message.edit_reply_markup(reply_markup=None)

    if callback_data.choice == "doctor":
        text = await triage.request_specialist(
            session,
            reason_code="user_requested_doctor",
            event=EventType.SPECIALIST_REQUESTED,
        )
        await state.clear()
        await callback.message.answer(
            texts.REFER_SPECIALIST_HEADER + text.strip(),
            reply_markup=specialist_kb(content.specialist_url),
        )
        await callback.answer()
        return

    # Самостоятельный путь начинается с вопросов безопасности, а не минует их.
    await callback.message.answer(texts.SELF_REHAB_SURVEY_FIRST)
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
