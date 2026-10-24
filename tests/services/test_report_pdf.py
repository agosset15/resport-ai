"""PDF-отчёт. Главное — не отдать пользователю файл с «кракозябрами».

Кириллица требует TTF: встроенные шрифты fpdf2 знают только latin-1. Если шрифта нет,
рендер обязан вернуть None, а бот — отправить текстовую версию.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from core.domain.enums import PlanSource
from core.services.report import ReportView, WellbeingRow
from infra.report.pdf import find_font, render_pdf


def demo_view() -> ReportView:
    return ReportView(
        plan_title="Самостоятельное восстановление",
        source=PlanSource.SCENARIO,
        scenario_title="Подвернул голеностоп",
        period_start=date(2026, 10, 18),
        period_end=date(2026, 10, 24),
        generated_at=datetime(2026, 10, 24, 9, 30, tzinfo=UTC),
        revisions=1,
        stage_lines=("1. Снять нагрузку — 3 дн. (текущий)", "2. Нагрузка — 7 дн."),
        completed_sessions=3,
        partial_sessions=1,
        skipped_sessions=1,
        no_data_days=2,
        total_sessions=10,
        percent=30,
        program_completed=False,
        wellbeing=(
            WellbeingRow(date(2026, 10, 18), 7, "умеренный", "кое-что труднее", "болит"),
            WellbeingRow(date(2026, 10, 24), 3, "небольшой", "всё как обычно", None),
        ),
        questions=("Можно ли увеличивать нагрузку?",),
        notes=("18.10: Ходьба — заболело после 10 минут",),
    )


class TestFontResolution:
    def test_configured_font_wins(self, tmp_path: Path) -> None:
        font = tmp_path / "custom.ttf"
        font.write_bytes(b"not a real font")
        assert find_font(font) == font

    def test_missing_configured_font_falls_back(self, tmp_path: Path) -> None:
        assert find_font(tmp_path / "nope.ttf") == find_font(None)


class TestRender:
    def test_renders_pdf_when_font_available(self) -> None:
        if find_font(None) is None:
            pytest.skip("в системе нет TTF с кириллицей")
        payload = render_pdf(demo_view())
        assert payload is not None
        assert payload.startswith(b"%PDF-")
        assert len(payload) > 1000

    def test_returns_none_without_font(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Лучше отдать текст, чем PDF, который невозможно прочитать."""
        monkeypatch.setattr("infra.report.pdf.FONT_CANDIDATES", ())
        assert render_pdf(demo_view()) is None

    def test_empty_period_still_renders(self) -> None:
        if find_font(None) is None:
            pytest.skip("в системе нет TTF с кириллицей")
        view = demo_view()
        empty = ReportView(
            plan_title=view.plan_title,
            source=view.source,
            scenario_title=view.scenario_title,
            period_start=view.period_start,
            period_end=view.period_end,
            generated_at=view.generated_at,
            revisions=0,
            stage_lines=view.stage_lines,
            completed_sessions=0,
            partial_sessions=0,
            skipped_sessions=0,
            no_data_days=7,
            total_sessions=None,
            percent=None,
            program_completed=False,
            questions=("Можно ли увеличивать нагрузку?",),
        )
        payload = render_pdf(empty)
        assert payload is not None
        assert payload.startswith(b"%PDF-")
