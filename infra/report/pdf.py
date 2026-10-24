"""PDF-версия отчёта на fpdf2.

Кириллица требует TTF-шрифта: встроенные шрифты fpdf2 знают только latin-1. Шрифт не
вшит в репозиторий — он берётся по пути из настроек либо из стандартных системных
расположений. В Docker его даёт пакет `fonts-dejavu-core` (см. Dockerfile).

Если шрифта нет, PDF не собирается: функция возвращает None, а вызывающий отправляет
текстовую версию отчёта. Молча отдавать PDF с «кракозябрами» нельзя — такой файл
пользователь понесёт врачу.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from core.services.report import ReportView
from infra.telemetry import get_logger

log = get_logger("report.pdf")

#: Где искать шрифт с кириллицей, если он не задан в настройках.
FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("C:/Windows/Fonts/segoeui.ttf"),
)

FONT_NAME = "report"
MARGIN = 15


def find_font(configured: Path | None = None) -> Path | None:
    if configured is not None and configured.is_file():
        return configured
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


class _Pdf(FPDF):
    def header(self) -> None:  # pragma: no cover — вызывает fpdf
        pass

    def footer(self) -> None:  # pragma: no cover — вызывает fpdf
        self.set_y(-12)
        self.set_font(FONT_NAME, size=8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 8, f"{self.page_no()}", align="C")


def _heading(pdf: _Pdf, text: str, size: int = 13) -> None:
    pdf.ln(3)
    pdf.set_font(FONT_NAME, size=size)
    pdf.set_text_color(20, 20, 20)
    pdf.multi_cell(0, 7, text)
    pdf.ln(1)


def _body(pdf: _Pdf, text: str, size: int = 10) -> None:
    pdf.set_font(FONT_NAME, size=size)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 5.5, text)


def render_pdf(view: ReportView, font_path: Path | None = None) -> bytes | None:
    """Байты PDF или None, если шрифта с кириллицей не нашлось."""
    font = find_font(font_path)
    if font is None:
        log.warning("report.font_missing", candidates=[str(p) for p in FONT_CANDIDATES])
        return None

    pdf = _Pdf(format="A4")
    pdf.set_margins(MARGIN, MARGIN, MARGIN)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font(FONT_NAME, fname=str(font))
    pdf.add_page()

    _heading(pdf, "Отчёт о восстановлении", size=16)
    _body(
        pdf,
        f"Период: {view.period_start:%d.%m.%Y} — {view.period_end:%d.%m.%Y}\n"
        f"Сформирован: {view.generated_at:%d.%m.%Y %H:%M} UTC",
        size=9,
    )

    _heading(pdf, "План")
    source_word = (
        "назначение специалиста"
        if view.source.value == "prescription"
        else "сценарий, проверенный специалистами"
    )
    plan_lines = [
        f"Травма: {view.scenario_title}",
        f"План: {view.plan_title}",
        f"Источник: {source_word}",
    ]
    if view.revisions:
        plan_lines.append(f"План менялся: {view.revisions} раз(а)")
    _body(pdf, "\n".join(plan_lines))

    _heading(pdf, "Выполнение")
    if view.percent is None:
        done_line = (
            f"Пройдено занятий: {view.completed_sessions}\n"
            "Полный объём программы не задан, общий процент не считается"
        )
    else:
        done_line = (
            f"Пройдено {view.completed_sessions} из {view.total_sessions} занятий "
            f"— {view.percent}% программы"
        )
    _body(
        pdf,
        done_line
        + f"\nЧастично выполнено: {view.partial_sessions} (в зачёт программы не идёт)"
        + f"\nПропущено: {view.skipped_sessions}"
        + f"\nНет данных: {view.no_data_days}"
        + ("\nПрограмма пройдена" if view.program_completed else ""),
    )

    _heading(pdf, "Этапы")
    _body(pdf, "\n".join(view.stage_lines))

    _heading(pdf, "Самочувствие")
    if view.wellbeing:
        pdf.set_font(FONT_NAME, size=9)
        widths = (24, 26, 42, 0)
        headers = ("Дата", "Боль 0–10", "Отёк", "Повседневные дела")
        for width, title in zip(widths, headers, strict=True):
            pdf.cell(width, 7, title, border="B")
        pdf.ln(7)
        for row in view.wellbeing:
            pdf.cell(widths[0], 6, f"{row.date:%d.%m}")
            pdf.cell(widths[1], 6, str(row.pain_0_10))
            pdf.cell(widths[2], 6, row.swelling)
            pdf.cell(widths[3], 6, row.daily_capacity)
            pdf.ln(6)
        notes = [row for row in view.wellbeing if row.note]
        if notes:
            pdf.ln(2)
            _body(
                pdf,
                "Заметки:\n" + "\n".join(f"• {row.date:%d.%m}: {row.note}" for row in notes),
                size=9,
            )
    else:
        _body(pdf, "Записей за период нет.")

    if view.notes:
        _heading(pdf, "Комментарии к упражнениям")
        _body(pdf, "\n".join(f"• {note}" for note in view.notes), size=9)

    _heading(pdf, "Вопросы к приёму")
    _body(
        pdf,
        "\n".join(f"{index}. {q}" for index, q in enumerate(view.questions, start=1)),
    )

    pdf.ln(4)
    pdf.set_font(FONT_NAME, size=8)
    pdf.set_text_color(120, 120, 120)
    pdf.multi_cell(
        0,
        4.5,
        "Отчёт собран ботом по отметкам пользователя. Это не диагноз и не медицинское "
        "заключение. Процент прохождения программы — про выполненные занятия, а не про "
        "то, насколько зажила травма.",
    )

    return bytes(pdf.output())
