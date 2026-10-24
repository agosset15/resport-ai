"""План на сегодня: карточки упражнений, отметки и комментарии.

Отметка «Выполнено / Частично / Пропущено» ставится по каждому пункту отдельно —
этого требует ТЗ, и этого не позволял старый чек-ин, где был только список ключей.
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
    ItemCB,
    daily_kb,
    item_kb,
)
from apps.bot.states import DiaryFlow
from core.domain.enums import ItemKind, ItemStatus
from core.services.daily import DailyPlanService
from core.services.dto import DailyItem, DailyPlanView
from core.services.supplements import SupplementService
from core.services.tracker import TrackerService
from core.services.user import UserService

router = Router(name="daily")

STATUS_BY_ACTION = {
    "done": ItemStatus.DONE,
    "partial": ItemStatus.PARTIAL,
    "skip": ItemStatus.SKIPPED,
}


def _item_card(item: DailyItem) -> str:
    """Карточка упражнения целиком: без неё пользователь не знает, что делать."""
    lines = [texts.ITEM_CARD_TITLE.format(title=item.title)]
    if item.instruction:
        lines.append(f"\n{item.instruction.strip()}")
    if item.dosage:
        lines.append(texts.ITEM_CARD_DOSAGE.format(dosage=item.dosage))
    if item.limits:
        limits = "\n".join(f"• {limit}" for limit in item.limits)
        lines.append(texts.ITEM_CARD_LIMITS.format(limits=limits))
    if item.lookup_hint:
        lines.append(texts.ITEM_CARD_LOOKUP.format(hint=item.lookup_hint))
    if item.kind is ItemKind.SUPPLEMENT:
        lines.append(texts.ITEM_CARD_SUPPLEMENT_NOTE)
    if item.status is not None:
        lines.append(texts.ITEM_CARD_STATUS.format(status=texts.ITEM_STATUS_LABELS[item.status]))
    if item.comment:
        lines.append(texts.ITEM_CARD_COMMENT.format(comment=item.comment))
    return "\n".join(lines)


async def _send_daily(message: Message, view: DailyPlanView) -> None:
    await message.answer(texts.daily_text(view), reply_markup=daily_kb(view))


@router.message(Command("today"))
@inject
async def today_command(
    message: Message,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    daily: FromDishka[DailyPlanService],
    supplements: FromDishka[SupplementService],
) -> None:
    if message.from_user is None:
        return
    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await message.answer(texts.NO_ACTIVE_PLAN)
        return
    active = await supplements.active_supplements(user)
    view = await daily.today(plan, timezone=user.timezone, supplements=active)
    await _send_daily(message, view)


@router.callback_query(DayCB.filter(F.action == "refresh"))
@inject
async def refresh_daily(
    callback: CallbackQuery,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    daily: FromDishka[DailyPlanService],
    supplements: FromDishka[SupplementService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await callback.answer(texts.NO_ACTIVE_PLAN, show_alert=True)
        return
    active = await supplements.active_supplements(user)
    view = await daily.today(plan, timezone=user.timezone, supplements=active)
    await callback.message.edit_text(texts.daily_text(view), reply_markup=daily_kb(view))
    await callback.answer()


@router.callback_query(ItemCB.filter(F.action == "open"))
@inject
async def open_item(
    callback: CallbackQuery,
    callback_data: ItemCB,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    daily: FromDishka[DailyPlanService],
    supplements: FromDishka[SupplementService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await callback.answer(texts.NO_ACTIVE_PLAN, show_alert=True)
        return

    kind = ItemKind(callback_data.kind)
    active = await supplements.active_supplements(user)
    item = await daily.item_of(
        plan, kind, callback_data.key, timezone=user.timezone, supplements=active
    )
    if item is None:
        await callback.answer(texts.ITEM_GONE, show_alert=True)
        return

    await callback.message.answer(_item_card(item), reply_markup=item_kb(item))
    await callback.answer()


@router.callback_query(ItemCB.filter(F.action.in_(tuple(STATUS_BY_ACTION))))
@inject
async def mark_item(
    callback: CallbackQuery,
    callback_data: ItemCB,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    daily: FromDishka[DailyPlanService],
    supplements: FromDishka[SupplementService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await callback.answer(texts.NO_ACTIVE_PLAN, show_alert=True)
        return

    kind = ItemKind(callback_data.kind)
    status = STATUS_BY_ACTION[callback_data.action]
    await daily.mark(plan, kind=kind, key=callback_data.key, status=status, timezone=user.timezone)

    active = await supplements.active_supplements(user)
    item = await daily.item_of(
        plan, kind, callback_data.key, timezone=user.timezone, supplements=active
    )
    if item is not None:
        await callback.message.edit_text(_item_card(item), reply_markup=item_kb(item))
    await callback.answer(texts.ITEM_MARKED.format(status=texts.ITEM_STATUS_LABELS[status]))


@router.callback_query(ItemCB.filter(F.action == "comment"))
async def ask_item_comment(
    callback: CallbackQuery, callback_data: ItemCB, state: FSMContext
) -> None:
    if not isinstance(callback.message, Message):
        return
    await state.set_state(DiaryFlow.waiting_item_comment)
    await state.update_data(item_kind=callback_data.kind, item_key=callback_data.key)
    await callback.message.answer(texts.ITEM_ASK_COMMENT)
    await callback.answer()


@router.message(DiaryFlow.waiting_item_comment, F.text)
@inject
async def save_item_comment(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    daily: FromDishka[DailyPlanService],
    supplements: FromDishka[SupplementService],
) -> None:
    if message.from_user is None or message.text is None:
        return
    data = await state.get_data()
    kind_raw, key = data.get("item_kind"), data.get("item_key")
    await state.set_state(None)

    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None or kind_raw is None or key is None:
        await message.answer(texts.NO_ACTIVE_PLAN)
        return

    await daily.set_comment(
        plan,
        kind=ItemKind(kind_raw),
        key=key,
        comment=message.text.strip(),
        timezone=user.timezone,
    )
    await message.answer(texts.ITEM_COMMENT_SAVED)
    active = await supplements.active_supplements(user)
    await _send_daily(message, await daily.today(plan, timezone=user.timezone, supplements=active))
