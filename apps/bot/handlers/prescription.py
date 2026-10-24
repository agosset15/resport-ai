"""План по назначению специалиста: второй способ формирования плана из ТЗ.

Бот переносит пункты назначения в карточки и расписание дословно и **не меняет
назначенную нагрузку**. Поэтому упражнения из нашей библиотеки сюда не подставляются:
они бы принесли с собой наши дозировки вместо дозировок врача.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from apps.bot.flow import start_plan_from_prescription
from apps.bot.keyboards.common import PrescriptionCB, prescription_kb
from apps.bot.states import PrescriptionFlow
from core.config import ContentSettings
from core.domain.enums import EventType
from core.llm.runner import LlmRunner
from core.llm.tasks.prescription import Prescription, parse_prescription
from core.services.tracker import TrackerService
from core.services.triage import TriageService
from core.services.user import UserService

router = Router(name="prescription")

MIN_PRESCRIPTION_LENGTH = 15


def _preview(parsed: Prescription) -> str:
    lines = [texts.PRESCRIPTION_PREVIEW_HEADER]
    lines += [f"{index}. {item}" for index, item in enumerate(parsed.items, start=1)]
    if parsed.limits:
        lines.append(texts.PRESCRIPTION_PREVIEW_LIMITS)
        lines += [f"• {limit}" for limit in parsed.limits]
    if parsed.duration_days:
        lines.append(texts.PRESCRIPTION_PREVIEW_DAYS.format(days=parsed.duration_days))
    if parsed.from_fallback:
        lines.append(texts.PRESCRIPTION_PREVIEW_FALLBACK)
    lines.append(texts.PRESCRIPTION_PREVIEW_FOOTER)
    return "\n".join(lines)


@router.message(Command("prescription"))
async def prescription_command(message: Message, state: FSMContext) -> None:
    await state.set_state(PrescriptionFlow.waiting_text)
    await message.answer(texts.PRESCRIPTION_ASK)


@router.message(PrescriptionFlow.waiting_text, F.text)
@inject
async def receive_prescription(
    message: Message,
    state: FSMContext,
    users: FromDishka[UserService],
    triage: FromDishka[TriageService],
    llm: FromDishka[LlmRunner],
) -> None:
    if message.from_user is None or message.text is None:
        return
    if len(message.text.strip()) < MIN_PRESCRIPTION_LENGTH:
        await message.answer(texts.PRESCRIPTION_TOO_SHORT)
        return

    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    session = await triage.active_session(user)
    if session is None or session.scenario_id is None:
        await message.answer(texts.PRESCRIPTION_NEEDS_SESSION)
        await state.clear()
        return

    parsed = await parse_prescription(llm, message.text, session_id=session.id)
    if parsed.is_empty:
        await message.answer(texts.PRESCRIPTION_NOT_PARSED)
        return

    await state.set_state(PrescriptionFlow.confirming)
    await state.update_data(
        items=list(parsed.items),
        limits=list(parsed.limits),
        duration_days=parsed.duration_days,
    )
    await message.answer(_preview(parsed), reply_markup=prescription_kb())


@router.callback_query(PrescriptionFlow.confirming, PrescriptionCB.filter())
@inject
async def confirm_prescription(
    callback: CallbackQuery,
    callback_data: PrescriptionCB,
    state: FSMContext,
    users: FromDishka[UserService],
    triage: FromDishka[TriageService],
    tracker: FromDishka[TrackerService],
    content: FromDishka[ContentSettings],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    await callback.message.edit_reply_markup(reply_markup=None)

    if not callback_data.accept:
        await state.set_state(PrescriptionFlow.waiting_text)
        await callback.message.answer(texts.PRESCRIPTION_RETRY)
        await callback.answer()
        return

    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    session = await triage.active_session(user)
    if session is None or session.scenario_id is None:
        await callback.answer(texts.NO_ACTIVE_SESSION, show_alert=True)
        await state.clear()
        return

    data = await state.get_data()
    await triage.note_event(
        session,
        EventType.PRESCRIPTION_PARSED,
        payload={"items": len(data.get("items", []))},
    )
    await start_plan_from_prescription(
        callback.message,
        state,
        triage=triage,
        tracker=tracker,
        content=content,
        session=session,
        items=list(data.get("items", [])),
        limits=list(data.get("limits", [])),
        duration_days=data.get("duration_days"),
        timezone=user.timezone,
    )
    await callback.answer()
