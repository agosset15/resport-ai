"""БАДы: анкета, карточки, журнал приёма и сообщения о реакциях.

Подбор делает детерминированный движок, LLM здесь не участвует. Жёсткие стопы снять
нельзя: подтверждение прочтения предупреждения их не отменяет, поэтому кнопки
«я понимаю, покажи всё равно» в этом экране нет и быть не должно.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from apps.bot.keyboards.common import (
    SupplementCB,
    specialist_kb,
    supplement_card_kb,
    supplement_list_kb,
    yes_no_kb,
)
from apps.bot.states import SupplementFlow
from core.config import ContentSettings
from core.domain.entities import User
from core.domain.enums import ReactionSeverity
from core.domain.supplement import SupplementRegistry
from core.services.supplements import SupplementService
from core.services.tracker import TrackerService
from core.services.user import UserService
from core.supplements.intake_form import QUESTIONS, AnswerKind, SupplementProfile, parse_list

router = Router(name="supplements")


def _question_text(index: int) -> str:
    question = QUESTIONS[index]
    body = texts.SUPPLEMENT_QUESTION.format(
        number=index + 1, total=len(QUESTIONS), text=question.text
    )
    if question.hint:
        body += texts.SUPPLEMENT_QUESTION_HINT.format(hint=question.hint)
    return body


async def _ask(message: Message, state: FSMContext, index: int) -> None:
    question = QUESTIONS[index]
    await state.set_state(SupplementFlow.asking)
    await state.update_data(question_index=index)
    markup = yes_no_kb() if question.kind is AnswerKind.YES_NO else None
    await message.answer(_question_text(index), reply_markup=markup)


@router.message(Command("supplements"))
@inject
async def supplements_command(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    service: FromDishka[SupplementService],
) -> None:
    if message.from_user is None:
        return
    user = await users.get_or_create(message.from_user.id, message.from_user.username)

    await message.answer(texts.SUPPLEMENT_INTRO)
    if await service.get_profile(user) is None:
        await state.update_data(answers={})
        await _ask(message, state, 0)
        return
    await _show_selection(message, user, service)


async def _show_selection(message: Message, user: User, service: SupplementService) -> None:
    selection = await service.selection(user)
    if selection is None:
        await message.answer(texts.SUPPLEMENT_NO_PROFILE)
        return

    if selection.is_suspended:
        reasons = "\n".join(f"• {texts.SUPPLEMENT_STOP_LABELS[stop]}" for stop in selection.stops)
        await message.answer(texts.SUPPLEMENT_SUSPENDED.format(reasons=reasons))
        return

    if not selection.recommended:
        await message.answer(texts.SUPPLEMENT_NOTHING_SUITABLE)
        return

    await message.answer(
        texts.SUPPLEMENT_LIST,
        reply_markup=supplement_list_kb(selection.recommended),
    )


@router.callback_query(SupplementFlow.asking, SupplementCB.filter(F.action.in_(("yes", "no"))))
@inject
async def answer_yes_no(
    callback: CallbackQuery,
    callback_data: SupplementCB,
    state: FSMContext,
    users: FromDishka[UserService],
    service: FromDishka[SupplementService],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await _store_answer(
        callback.message,
        state,
        users,
        service,
        callback.from_user.id,
        callback.from_user.username,
        value=callback_data.action == "yes",
    )
    await callback.answer()


@router.message(SupplementFlow.asking, F.text)
@inject
async def answer_text(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    service: FromDishka[SupplementService],
) -> None:
    if message.from_user is None or message.text is None:
        return
    data = await state.get_data()
    index = int(data.get("question_index", 0))
    question = QUESTIONS[index]

    if question.kind is AnswerKind.NUMBER:
        cleaned = message.text.strip()
        if not cleaned.isdigit():
            await message.answer(texts.SUPPLEMENT_NEED_NUMBER)
            return
        value: object = int(cleaned)
    elif question.kind is AnswerKind.YES_NO:
        await message.answer(texts.SUPPLEMENT_NEED_BUTTON, reply_markup=yes_no_kb())
        return
    else:
        value = list(parse_list(message.text))

    await _store_answer(
        message,
        state,
        users,
        service,
        message.from_user.id,
        message.from_user.username,
        value=value,
    )


async def _store_answer(
    message: Message,
    state: FSMContext,
    users: UserService,
    service: SupplementService,
    tg_id: int,
    username: str | None,
    *,
    value: object,
) -> None:
    data = await state.get_data()
    index = int(data.get("question_index", 0))
    answers = dict(data.get("answers", {}))
    answers[QUESTIONS[index].key.value] = value
    await state.update_data(answers=answers)

    if index + 1 < len(QUESTIONS):
        await _ask(message, state, index + 1)
        return

    await state.set_state(None)
    user = await users.get_or_create(tg_id, username)
    profile = SupplementProfile.from_answers(answers)
    await service.save_profile(user, profile)
    await message.answer(texts.SUPPLEMENT_PROFILE_SAVED)
    await _show_selection(message, user, service)


@router.callback_query(SupplementCB.filter(F.action == "open"))
@inject
async def open_card(
    callback: CallbackQuery,
    callback_data: SupplementCB,
    registry: FromDishka[SupplementRegistry],
) -> None:
    if not isinstance(callback.message, Message):
        return
    supplement = registry.get(callback_data.supplement_id)
    if supplement is None:
        await callback.answer(texts.SUPPLEMENT_GONE, show_alert=True)
        return
    await callback.message.answer(
        texts.supplement_card(supplement), reply_markup=supplement_card_kb(supplement)
    )
    await callback.answer()


@router.callback_query(SupplementCB.filter(F.action.in_(("add", "skip"))))
@inject
async def add_or_skip(
    callback: CallbackQuery,
    callback_data: SupplementCB,
    users: FromDishka[UserService],
    service: FromDishka[SupplementService],
    registry: FromDishka[SupplementRegistry],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    supplement = registry.get(callback_data.supplement_id)
    if supplement is None:
        await callback.answer(texts.SUPPLEMENT_GONE, show_alert=True)
        return

    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    await callback.message.edit_reply_markup(reply_markup=None)

    if callback_data.action == "add":
        await service.add_to_plan(user, supplement)
        await callback.message.answer(texts.SUPPLEMENT_ADDED.format(product=supplement.product))
    else:
        await service.decline(user, supplement)
        await callback.message.answer(texts.SUPPLEMENT_DECLINED)
    await callback.answer()


@router.callback_query(SupplementCB.filter(F.action == "reaction"))
async def ask_reaction(
    callback: CallbackQuery, callback_data: SupplementCB, state: FSMContext
) -> None:
    if not isinstance(callback.message, Message):
        return
    await state.set_state(SupplementFlow.reporting_reaction)
    await state.update_data(supplement_id=callback_data.supplement_id)
    await callback.message.answer(texts.SUPPLEMENT_ASK_REACTION)
    await callback.answer()


@router.message(SupplementFlow.reporting_reaction, F.text)
@inject
async def save_reaction(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    service: FromDishka[SupplementService],
    content: FromDishka[ContentSettings],
) -> None:
    if message.from_user is None or message.text is None:
        return
    data = await state.get_data()
    supplement_id = data.get("supplement_id")
    await state.set_state(None)
    if supplement_id is None:
        await message.answer(texts.SUPPLEMENT_GONE)
        return

    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    severity = await service.report_reaction(user, supplement_id, message.text.strip())

    if severity is ReactionSeverity.SEVERE:
        await message.answer(texts.SUPPLEMENT_REACTION_SEVERE)
    else:
        await message.answer(
            texts.SUPPLEMENT_REACTION_MILD, reply_markup=specialist_kb(content.specialist_url)
        )


@router.message(Command("my_supplements"))
@inject
async def my_supplements(
    message: Message,
    users: FromDishka[UserService],
    service: FromDishka[SupplementService],
    tracker: FromDishka[TrackerService],
) -> None:
    if message.from_user is None:
        return
    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    active = await service.active_supplements(user)
    if not active:
        await message.answer(texts.SUPPLEMENT_NONE_ACTIVE)
        return
    await message.answer(texts.SUPPLEMENT_ACTIVE_LIST, reply_markup=supplement_list_kb(active))
