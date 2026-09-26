"""/start, дисклеймер и согласие, выбор спорта, приём жалобы."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from apps.bot.flow import advance
from apps.bot.keyboards.common import (
    ConsentCB,
    ScenarioCB,
    SportCB,
    consent_kb,
    scenarios_kb,
    sports_kb,
)
from apps.bot.states import TriageFlow
from core.config import ContentSettings
from core.domain.enums import Sport
from core.domain.scenario import ScenarioRegistry
from core.services.tracker import TrackerService
from core.services.triage import TriageService
from core.services.user import UserService

router = Router(name="onboarding")

MIN_COMPLAINT_LENGTH = 10


@router.message(CommandStart())
@inject
async def start(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    registry: FromDishka[ScenarioRegistry],
) -> None:
    await state.clear()
    if message.from_user is None:
        return
    user = await users.get_or_create(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        locale=message.from_user.language_code or "ru",
    )

    await message.answer(texts.START)
    if users.needs_consent(user):
        await message.answer(texts.DISCLAIMER, reply_markup=consent_kb())
        return
    await message.answer(texts.CHOOSE_SPORT, reply_markup=sports_kb(registry.sports()))


@router.callback_query(ConsentCB.filter(F.accept == True))  # noqa: E712
@inject
async def accept_consent(
    callback: CallbackQuery,
    users: FromDishka[UserService],
    registry: FromDishka[ScenarioRegistry],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    await users.accept_consent(user)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(texts.CONSENT_ACCEPTED)
    await callback.message.answer(texts.CHOOSE_SPORT, reply_markup=sports_kb(registry.sports()))
    await callback.answer()


@router.callback_query(SportCB.filter())
@inject
async def choose_sport(
    callback: CallbackQuery,
    callback_data: SportCB,
    state: FSMContext,
    users: FromDishka[UserService],
    triage: FromDishka[TriageService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    if users.needs_consent(user):
        await callback.answer(texts.CONSENT_REQUIRED, show_alert=True)
        return

    session = await triage.start_session(user, Sport(callback_data.sport))
    await state.set_state(TriageFlow.waiting_complaint)
    await state.update_data(session_id=str(session.id))
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(texts.DESCRIBE_PROBLEM)
    await callback.answer()


@router.message(TriageFlow.waiting_complaint, F.text)
@inject
async def receive_complaint(
    message: Message,
    state: FSMContext,
    triage: FromDishka[TriageService],
    tracker: FromDishka[TrackerService],
    content: FromDishka[ContentSettings],
    users: FromDishka[UserService],
) -> None:
    if message.from_user is None or message.text is None:
        return
    if len(message.text.strip()) < MIN_COMPLAINT_LENGTH:
        await message.answer(texts.COMPLAINT_TOO_SHORT)
        return

    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    session = await triage.active_session(user)
    if session is None:
        await message.answer(texts.NO_ACTIVE_SESSION)
        await state.clear()
        return

    result = await triage.submit_complaint(session, message.text)
    if result.needs_manual_choice:
        await message.answer(texts.CLASSIFY_FALLBACK, reply_markup=scenarios_kb(result.choices))
        return

    session = await triage.get_session(session.id)
    assert session is not None
    scenario = triage.scenario_of(session)
    await message.answer(texts.CLASSIFY_OK.format(title=scenario.title))
    await advance(
        message,
        state,
        triage=triage,
        tracker=tracker,
        content=content,
        session_id=session.id,
        timezone=user.timezone,
    )


@router.callback_query(ScenarioCB.filter())
@inject
async def choose_scenario(
    callback: CallbackQuery,
    callback_data: ScenarioCB,
    state: FSMContext,
    triage: FromDishka[TriageService],
    tracker: FromDishka[TrackerService],
    content: FromDishka[ContentSettings],
    users: FromDishka[UserService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    session = await triage.active_session(user)
    if session is None:
        await callback.answer(texts.NO_ACTIVE_SESSION, show_alert=True)
        return

    session = await triage.select_scenario(session, callback_data.scenario_id)
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


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(texts.HELP)
