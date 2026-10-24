"""Отчёт за период: превью в чате, затем файл — PDF или текст.

Отчёт пользователь смотрит сам и при желании передаёт врачу, поэтому сначала короткое
превью в сообщении, а файл — по кнопке.
"""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from dishka.integrations.aiogram import FromDishka, inject

from apps.bot import texts
from apps.bot.keyboards.common import ReportCB, report_kb
from core.config import ContentSettings
from core.services.report import ReportService, ReportView, report_markdown
from core.services.tracker import TrackerService
from core.services.user import UserService
from infra.report.pdf import render_pdf

router = Router(name="report")


def _preview(view: ReportView) -> str:
    total_part = (
        texts.REPORT_PREVIEW_TOTAL.format(total=view.total_sessions, percent=view.percent)
        if view.percent is not None
        else ""
    )
    return (
        texts.REPORT_PREVIEW_HEADER.format(
            start=f"{view.period_start:%d.%m}", end=f"{view.period_end:%d.%m}"
        )
        + texts.REPORT_PREVIEW_BODY.format(
            done=view.completed_sessions,
            total_part=total_part,
            partial=view.partial_sessions,
            skipped=view.skipped_sessions,
            no_data=view.no_data_days,
            wellbeing=len(view.wellbeing),
            questions=len(view.questions),
        )
        + texts.REPORT_PREVIEW_FOOTER
    )


@router.message(Command("report"))
@inject
async def report_command(
    message: Message,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    reports: FromDishka[ReportService],
    content: FromDishka[ContentSettings],
) -> None:
    if message.from_user is None:
        return
    user = await users.get_or_create(message.from_user.id, message.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await message.answer(texts.NO_ACTIVE_PLAN)
        return

    view = await reports.build(plan, days=content.report_period_days, timezone=user.timezone)
    if not view.wellbeing and not view.completed_sessions and not view.partial_sessions:
        await message.answer(texts.REPORT_NO_DATA)
        return

    await message.answer(_preview(view), reply_markup=report_kb())


@router.callback_query(ReportCB.filter())
@inject
async def send_report_file(
    callback: CallbackQuery,
    callback_data: ReportCB,
    users: FromDishka[UserService],
    tracker: FromDishka[TrackerService],
    reports: FromDishka[ReportService],
    content: FromDishka[ContentSettings],
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        return
    user = await users.get_or_create(callback.from_user.id, callback.from_user.username)
    plan = await tracker.active_plan(user)
    if plan is None:
        await callback.answer(texts.NO_ACTIVE_PLAN, show_alert=True)
        return

    view = await reports.build(plan, days=content.report_period_days, timezone=user.timezone)
    await callback.answer()

    if callback_data.fmt == "pdf":
        payload = render_pdf(view, content.report_font_path)
        if payload is not None:
            await callback.message.answer_document(
                BufferedInputFile(payload, filename=f"{view.filename_stem}.pdf")
            )
            return
        # Шрифта с кириллицей нет: PDF был бы нечитаемым, отдаём текст.
        await callback.message.answer(texts.REPORT_PDF_UNAVAILABLE)

    await callback.message.answer_document(
        BufferedInputFile(
            report_markdown(view).encode("utf-8"),
            filename=f"{view.filename_stem}.md",
        )
    )
