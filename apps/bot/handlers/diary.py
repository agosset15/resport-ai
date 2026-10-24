"""Дневник самочувствия: одни и те же вопросы каждый день.

Вопросы фиксированы намеренно — иначе динамику не с чем сравнивать. Шаги: боль 0–10,
отёк, что получается в быту, затем необязательная заметка.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from apps.bot.keyboards.common import (
    DayCB,
    WellbeingCB,
    capacity_kb,
    pain_kb,
    swelling_kb,
)
from apps.bot.states import DiaryFlow
from core.domain.enums import DailyCapacity, Swelling
from core.services.daily import DailyPlanService
from core.services.diary_service import DiaryService
from core.services.dto import WellbeingView
from core.services.tracker import TrackerService
from core.services.user import UserService

router = Router(name="diary")

SKIP_WORDS = frozenset({"-", "нет", "пропустить", "/skip"})


@router.message(Command("diary"))
@inject
async def diary_command(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    daily: FromDishka[DailyPlanService],
) -> None:
    if message.from_user is None:
        return
    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await message.answer(texts.NO_ACTIVE_PLAN)
        return

    view = await daily.today(plan, timezone=user.timezone)
    if view.wellbeing_done:
        await message.answer(texts.WELLBEING_ALREADY_DONE)
    await _ask_pain(message, state)


@router.callback_query(DayCB.filter(F.action == "wellbeing"))
async def start_wellbeing(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    await _ask_pain(callback.message, state)
    await callback.answer()


async def _ask_pain(message: Message, state: FSMContext) -> None:
    await state.set_state(DiaryFlow.waiting_pain)
    await state.update_data(wellbeing={})
    await message.answer(texts.WELLBEING_ASK_PAIN, reply_markup=pain_kb())


@router.callback_query(DiaryFlow.waiting_pain, WellbeingCB.filter(F.field == "pain"))
async def got_pain(callback: CallbackQuery, callback_data: WellbeingCB, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    await state.update_data(wellbeing={"pain_0_10": int(callback_data.value)})
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(DiaryFlow.waiting_pain)
    await callback.message.answer(texts.WELLBEING_ASK_SWELLING, reply_markup=swelling_kb())
    await callback.answer()


@router.callback_query(WellbeingCB.filter(F.field == "swelling"))
async def got_swelling(
    callback: CallbackQuery, callback_data: WellbeingCB, state: FSMContext
) -> None:
    if not isinstance(callback.message, Message):
        return
    data = await state.get_data()
    answers = dict(data.get("wellbeing", {}))
    answers["swelling"] = callback_data.value
    await state.update_data(wellbeing=answers)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(texts.WELLBEING_ASK_CAPACITY, reply_markup=capacity_kb())
    await callback.answer()


@router.callback_query(WellbeingCB.filter(F.field == "capacity"))
async def got_capacity(
    callback: CallbackQuery, callback_data: WellbeingCB, state: FSMContext
) -> None:
    if not isinstance(callback.message, Message):
        return
    data = await state.get_data()
    answers = dict(data.get("wellbeing", {}))
    answers["daily_capacity"] = callback_data.value
    await state.update_data(wellbeing=answers)
    await state.set_state(DiaryFlow.waiting_wellbeing_note)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(texts.WELLBEING_ASK_NOTE)
    await callback.answer()


@router.message(DiaryFlow.waiting_wellbeing_note, F.text)
@inject
async def got_note(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    daily: FromDishka[DailyPlanService],
) -> None:
    if message.from_user is None or message.text is None:
        return
    data = await state.get_data()
    answers = dict(data.get("wellbeing", {}))
    await state.set_state(None)

    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await message.answer(texts.NO_ACTIVE_PLAN)
        return

    raw_note = message.text.strip()
    note = None if raw_note.casefold() in SKIP_WORDS else raw_note

    # Пропущенные шаги не выдумываем: без боли и отёка записи нет.
    if "pain_0_10" not in answers or "swelling" not in answers:
        await message.answer(texts.WELLBEING_INCOMPLETE)
        await _ask_pain(message, state)
        return

    await daily.log_wellbeing(
        plan,
        WellbeingView(
            pain_0_10=int(answers["pain_0_10"]),
            swelling=Swelling(answers["swelling"]),
            daily_capacity=DailyCapacity(answers.get("daily_capacity", DailyCapacity.LIMITED)),
            note=note,
        ),
        timezone=user.timezone,
    )
    await message.answer(texts.WELLBEING_SAVED)


@router.message(Command("progress"))
@inject
async def progress_command(
    message: Message,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    diary: FromDishka[DiaryService],
) -> None:
    if message.from_user is None:
        return
    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await message.answer(texts.NO_ACTIVE_PLAN)
        return

    view = await diary.progress(plan, timezone=user.timezone)
    revisions = await diary.revision_count(plan)
    await message.answer(texts.progress_text(view, revisions))
