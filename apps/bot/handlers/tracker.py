"""Трекер: /plan, чек-ин, напоминания."""

from __future__ import annotations

from datetime import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from apps.bot.keyboards.common import (
    CheckinCB,
    ReminderCB,
    TaskCB,
    feeling_kb,
    reminder_kb,
    specialist_kb,
    tasks_kb,
)
from apps.bot.renderers import send_stage
from apps.bot.states import TrackerFlow
from core.config import ContentSettings
from core.domain.entities import RecoveryPlan
from core.domain.enums import Feeling
from core.scenarios.plan_engine import TrackerAction
from core.services.tracker import TrackerService
from core.services.user import UserService

router = Router(name="tracker")


@router.message(Command("plan"))
@inject
async def show_plan(
    message: Message,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
) -> None:
    if message.from_user is None:
        return
    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await message.answer(texts.NO_ACTIVE_PLAN)
        return
    await send_stage(message, await tracker.today_view(plan, timezone=user.timezone))


@router.message(Command("checkin"))
@inject
async def checkin_command(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
) -> None:
    if message.from_user is None:
        return
    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await message.answer(texts.NO_ACTIVE_PLAN)
        return
    await _start_checkin(message, state, tracker, plan, user.timezone)


@router.callback_query(CheckinCB.filter(F.action == "start"))
@inject
async def checkin_start(
    callback: CallbackQuery,
    state: FSMContext,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await callback.answer(texts.NO_ACTIVE_PLAN, show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await _start_checkin(callback.message, state, tracker, plan, user.timezone)
    await callback.answer()


async def _start_checkin(
    message: Message,
    state: FSMContext,
    tracker: TrackerService,
    plan: RecoveryPlan,
    timezone: str,
) -> None:
    view = await tracker.today_view(plan, timezone=timezone)
    if view.checkin_done_today:
        await send_stage(message, view)
        return
    await state.set_state(TrackerFlow.collecting_tasks)
    await state.update_data(plan_id=str(plan.id), tasks=[])
    await message.answer(texts.CHECKIN_PROMPT_TASKS, reply_markup=tasks_kb(view.tasks, selected=()))


@router.callback_query(TrackerFlow.collecting_tasks, TaskCB.filter())
@inject
async def toggle_task(
    callback: CallbackQuery,
    callback_data: TaskCB,
    state: FSMContext,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    data = await state.get_data()
    selected: list[str] = list(data.get("tasks", []))
    if callback_data.key in selected:
        selected.remove(callback_data.key)
    else:
        selected.append(callback_data.key)
    await state.update_data(tasks=selected)

    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await callback.answer(texts.NO_ACTIVE_PLAN, show_alert=True)
        return
    view = tracker.stage_view(plan, timezone=user.timezone)
    await callback.message.edit_reply_markup(reply_markup=tasks_kb(view.tasks, selected=selected))
    await callback.answer()


@router.callback_query(TrackerFlow.collecting_tasks, CheckinCB.filter(F.action == "tasks_done"))
async def ask_feeling(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(texts.CHECKIN_PROMPT_FEELING, reply_markup=feeling_kb())
    await callback.answer()


@router.callback_query(CheckinCB.filter(F.action == "feeling"))
@inject
async def submit_feeling(
    callback: CallbackQuery,
    callback_data: CheckinCB,
    state: FSMContext,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    content: FromDishka[ContentSettings],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return

    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await callback.answer(texts.NO_ACTIVE_PLAN, show_alert=True)
        return

    data = await state.get_data()
    tasks_done = list(data.get("tasks", []))
    result = await tracker.submit_checkin(
        plan,
        feeling=Feeling(callback_data.value),
        tasks_done=tasks_done,
        timezone=user.timezone,
    )
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(texts.CHECKIN_SAVED)

    if result.action is TrackerAction.ESCALATE:
        await callback.message.answer(
            texts.PLAN_ESCALATED.format(text=result.text.strip()),
            reply_markup=specialist_kb(content.specialist_url),
        )
        return

    if result.action is TrackerAction.COMPLETE:
        await callback.message.answer(texts.PLAN_COMPLETED.format(text=result.text.strip()))
        return

    if result.action is TrackerAction.ADVANCE:
        await callback.message.answer(texts.STAGE_ADVANCED.format(text=result.text))
        if result.stage is not None:
            await send_stage(callback.message, result.stage)
        return

    await callback.message.answer(result.text)


@router.message(Command("reminder"))
async def reminder_command(message: Message, state: FSMContext) -> None:
    await state.set_state(TrackerFlow.waiting_reminder_time)
    await message.answer(texts.ASK_REMINDER_TIME, reply_markup=reminder_kb())


@router.callback_query(ReminderCB.filter())
@inject
async def set_reminder(
    callback: CallbackQuery,
    callback_data: ReminderCB,
    state: FSMContext,
    users: FromDishka[UserService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.set_state(None)

    if callback_data.value == "skip":
        await callback.message.answer("Хорошо, напоминать не буду. Чек-ин — командой /checkin.")
        await callback.answer()
        return

    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    parsed = _parse_time(callback_data.value)
    if parsed is None:
        await callback.answer(texts.REMINDER_BAD_FORMAT, show_alert=True)
        return
    await users.set_reminder(user, parsed)
    await callback.message.answer(texts.REMINDER_SET.format(time=callback_data.value))
    await callback.answer()


@router.message(TrackerFlow.waiting_reminder_time, F.text)
@inject
async def set_reminder_text(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
) -> None:
    if message.from_user is None or message.text is None:
        return
    parsed = _parse_time(message.text)
    if parsed is None:
        await message.answer(texts.REMINDER_BAD_FORMAT)
        return
    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    await users.set_reminder(user, parsed)
    await state.set_state(None)
    await message.answer(texts.REMINDER_SET.format(time=parsed.strftime("%H:%M")))


def _parse_time(raw: str) -> time | None:
    cleaned = raw.strip().replace(".", ":").replace(" ", "")
    if ":" not in cleaned:
        cleaned = f"{cleaned}:00"
    try:
        hours, minutes = (int(part) for part in cleaned.split(":", 1))
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return time(hour=hours, minute=minutes)
