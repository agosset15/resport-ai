"""План на сегодня и отчёт: сборка из снимка, отметки, вопросы к приёму."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from core.domain.entities import RecoveryPlan
from core.domain.enums import (
    DailyCapacity,
    EventType,
    ItemKind,
    ItemStatus,
    PlanSource,
    Swelling,
)
from core.domain.scenario import ScenarioRegistry
from core.scenarios.exercises import load_library
from core.scenarios.snapshot import (
    SNAPSHOT_FORMAT,
    exercises_from_snapshot,
    plan_from_snapshot,
    plan_to_snapshot,
)
from core.services.daily import DailyPlanService
from core.services.dto import WellbeingView
from core.services.report import ReportService, build_questions, report_markdown
from tests.fakes import (
    FakeEventRepository,
    FakePlanItemRepository,
    FakePlanRevisionRepository,
    FakeSessionRepository,
    FakeWellbeingRepository,
)

TODAY = date(2026, 10, 24)


@pytest.fixture(scope="module")
def library():
    return load_library()


@pytest.fixture
def snapshot(registry: ScenarioRegistry, library):
    scenario = registry.require("football.bruise")
    plan_def = scenario.plans["bruise_basic"]
    return plan_to_snapshot(scenario, plan_def, library)


@pytest.fixture
def plan(snapshot) -> RecoveryPlan:
    started = datetime(2026, 10, 24, 8, 0, tzinfo=UTC)
    return RecoveryPlan(
        id=uuid4(),
        session_id=uuid4(),
        plan_key="bruise_basic",
        plan_snapshot=snapshot,
        started_at=started,
        stage_started_at=started,
    )


class Harness:
    def __init__(self) -> None:
        self.items = FakePlanItemRepository()
        self.wellbeing = FakeWellbeingRepository()
        self.revisions = FakePlanRevisionRepository()
        self.sessions = FakeSessionRepository()
        self.events = FakeEventRepository()
        self.daily = DailyPlanService(self.items, self.wellbeing, self.sessions, self.events)
        self.reports = ReportService(
            self.items, self.wellbeing, self.revisions, self.sessions, self.events
        )


@pytest.fixture
def harness() -> Harness:
    return Harness()


class TestSnapshot:
    def test_format_is_two(self, snapshot) -> None:
        assert snapshot["format"] == SNAPSHOT_FORMAT == 2

    def test_cards_are_inlined(self, snapshot) -> None:
        """Правка библиотеки не должна менять упражнения тому, кто уже в плане."""
        cards = exercises_from_snapshot(snapshot)
        assert cards
        for stage in plan_from_snapshot(snapshot).stages:
            for exercise_id in stage.exercises:
                assert exercise_id in cards

    def test_old_format_still_readable(self, snapshot) -> None:
        legacy = dict(snapshot)
        legacy["format"] = 1
        legacy.pop("exercises")
        for stage in legacy["stages"]:
            stage.pop("exercises", None)
        assert exercises_from_snapshot(legacy) == {}
        assert plan_from_snapshot(legacy).stages[0].exercises == ()


class TestToday:
    async def test_items_come_from_snapshot(self, harness: Harness, plan) -> None:
        view = await harness.daily.today(plan, day=TODAY)
        assert view.items
        kinds = {item.kind for item in view.items}
        assert ItemKind.EXERCISE in kinds
        assert ItemKind.TASK in kinds

    async def test_exercise_card_is_complete(self, harness: Harness, plan) -> None:
        """Карточка обязана содержать то, что требует ТЗ."""
        view = await harness.daily.today(plan, day=TODAY)
        exercise = next(i for i in view.items if i.kind is ItemKind.EXERCISE)
        assert exercise.instruction
        assert exercise.dosage
        assert exercise.limits
        assert exercise.lookup_hint and "интернете" in exercise.lookup_hint

    async def test_nothing_marked_initially(self, harness: Harness, plan) -> None:
        view = await harness.daily.today(plan, day=TODAY)
        assert view.done == view.partial == view.skipped == 0
        assert not view.all_marked

    async def test_mark_is_reflected(self, harness: Harness, plan) -> None:
        view = await harness.daily.today(plan, day=TODAY)
        first = view.items[0]
        await harness.daily.mark(
            plan, kind=first.kind, key=first.key, status=ItemStatus.DONE, day=TODAY
        )

        updated = await harness.daily.today(plan, day=TODAY)
        assert updated.done == 1
        assert updated.item(first.kind, first.key).status is ItemStatus.DONE  # type: ignore[union-attr]
        assert EventType.PLAN_ITEM_MARKED in harness.events.types()

    async def test_remark_replaces_previous(self, harness: Harness, plan) -> None:
        view = await harness.daily.today(plan, day=TODAY)
        first = view.items[0]
        for status in (ItemStatus.DONE, ItemStatus.SKIPPED):
            await harness.daily.mark(plan, kind=first.kind, key=first.key, status=status, day=TODAY)

        updated = await harness.daily.today(plan, day=TODAY)
        assert updated.done == 0
        assert updated.skipped == 1

    async def test_comment_keeps_status(self, harness: Harness, plan) -> None:
        view = await harness.daily.today(plan, day=TODAY)
        first = view.items[0]
        await harness.daily.mark(
            plan, kind=first.kind, key=first.key, status=ItemStatus.DONE, day=TODAY
        )
        await harness.daily.set_comment(
            plan, kind=first.kind, key=first.key, comment="было тяжело", day=TODAY
        )

        item = (await harness.daily.today(plan, day=TODAY)).item(first.kind, first.key)
        assert item is not None
        assert item.status is ItemStatus.DONE
        assert item.comment == "было тяжело"

    async def test_prescription_source_is_visible(self, harness: Harness, plan) -> None:
        plan.source = PlanSource.PRESCRIPTION
        view = await harness.daily.today(plan, day=TODAY)
        assert view.source is PlanSource.PRESCRIPTION

    async def test_wellbeing_flag(self, harness: Harness, plan) -> None:
        assert not (await harness.daily.today(plan, day=TODAY)).wellbeing_done
        await harness.daily.log_wellbeing(
            plan,
            WellbeingView(pain_0_10=4, swelling=Swelling.MILD, daily_capacity=DailyCapacity.FULL),
            day=TODAY,
        )
        assert (await harness.daily.today(plan, day=TODAY)).wellbeing_done
        assert EventType.WELLBEING_LOGGED in harness.events.types()

    async def test_pain_is_clamped(self, harness: Harness, plan) -> None:
        await harness.daily.log_wellbeing(
            plan,
            WellbeingView(pain_0_10=42, swelling=Swelling.NONE, daily_capacity=DailyCapacity.FULL),
            day=TODAY,
        )
        stored = await harness.wellbeing.get_for_date(plan.id, TODAY)
        assert stored is not None
        assert stored.pain_0_10 == 10


class TestQuestions:
    def test_pain_not_improving_raises_a_question(self) -> None:
        from tests.services.test_progress import wellbeing

        questions = build_questions([], [wellbeing(0, 5), wellbeing(3, 6)])
        assert any("не уменьшилась" in q for q in questions)

    def test_always_asks_about_load(self) -> None:
        assert any("нагрузку" in q for q in build_questions([], []))

    def test_skipped_items_are_named(self) -> None:
        from tests.services.test_progress import item

        questions = build_questions(
            [item(0, ItemStatus.SKIPPED, "calm_walk")],
            [],
            titles={"calm_walk": "Спокойная ходьба"},
        )
        assert any("Спокойная ходьба" in q for q in questions)


class TestReport:
    async def test_report_has_required_wording(self, harness: Harness, plan) -> None:
        view = await harness.daily.today(plan, day=TODAY)
        await harness.daily.mark(
            plan,
            kind=view.items[0].kind,
            key=view.items[0].key,
            status=ItemStatus.DONE,
            day=TODAY,
        )
        await harness.daily.log_wellbeing(
            plan,
            WellbeingView(pain_0_10=3, swelling=Swelling.MILD, daily_capacity=DailyCapacity.FULL),
            day=TODAY,
        )

        report = await harness.reports.build(plan, days=14)
        text = report_markdown(report)

        assert "Отчёт о восстановлении" in text
        assert "в зачёт программы не идёт" in text
        assert "Вопросы к приёму" in text
        assert "не диагноз" in text
        assert EventType.REPORT_BUILT in harness.events.types()

    async def test_report_records_plan_source(self, harness: Harness, plan) -> None:
        plan.source = PlanSource.PRESCRIPTION
        report = await harness.reports.build(plan, days=7)
        assert "назначение специалиста" in report_markdown(report)
