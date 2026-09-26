"""Отрисовка DTO в сообщения Telegram. Никаких решений — только представление."""

from __future__ import annotations

from aiogram.types import Message

from apps.bot import texts
from apps.bot.keyboards.common import options_kb, specialist_kb
from core.domain.enums import Outcome
from core.services.dto import OutcomeView, QuestionView, StageView


async def send_question(message: Message, view: QuestionView) -> None:
    body = texts.QUESTION.format(number=view.number, total=view.total, text=view.question.text)
    if view.question.hint:
        body += texts.QUESTION_HINT.format(hint=view.question.hint)
    if view.question.allow_free_text:
        body += texts.FREE_TEXT_ALLOWED
    await message.answer(body, reply_markup=options_kb(view.question.key, view.options))


async def send_referral(message: Message, view: OutcomeView, specialist_url: str) -> None:
    body = texts.REFER_SPECIALIST_HEADER + view.text.strip() + texts.REFER_SPECIALIST_FOOTER
    await message.answer(body, reply_markup=specialist_kb(specialist_url))


async def send_plan_intro(message: Message, view: OutcomeView) -> None:
    await message.answer(texts.PLAN_INTRO_HEADER + view.text.strip())


async def send_outcome(message: Message, view: OutcomeView, specialist_url: str) -> None:
    if view.outcome is Outcome.REFER_SPECIALIST:
        await send_referral(message, view, specialist_url)
    else:
        await send_plan_intro(message, view)


def stage_body(view: StageView) -> str:
    return texts.stage_text(
        plan_title=view.plan_title,
        stage_number=view.stage_index + 1,
        stage_total=view.stage_total,
        stage_title=view.stage_title,
        day_number=view.day_number,
        day_total=view.day_total,
        description=view.stage_description,
        tasks=[task.text for task in view.tasks],
        done=view.checkin_done_today,
    )


async def send_stage(message: Message, view: StageView) -> None:
    from apps.bot.keyboards.common import checkin_start_kb

    await message.answer(
        stage_body(view),
        reply_markup=None if view.checkin_done_today else checkin_start_kb(),
    )
