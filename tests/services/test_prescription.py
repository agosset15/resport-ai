"""План по назначению специалиста.

Главное требование ТЗ: бот переносит назначение дословно и не меняет назначенную
нагрузку. Поэтому упражнения из нашей библиотеки в такой план не подставляются —
они принесли бы наши дозировки вместо дозировок врача.
"""

from __future__ import annotations

import pytest

from core.config import LlmSettings
from core.domain.enums import EventType, ItemKind, PlanSource, Sport
from core.domain.scenario import ScenarioRegistry
from core.llm.runner import LlmRunner
from core.llm.tasks.prescription import parse_prescription, split_plainly
from core.scenarios.exercises import load_library
from core.scenarios.snapshot import exercises_from_snapshot
from core.services.daily import DailyPlanService
from core.services.tracker import TrackerService
from tests.fakes import (
    FakeCheckinRepository,
    FakeEventRepository,
    FakeLlmCallRepository,
    FakePlanItemRepository,
    FakePlanRepository,
    FakeSessionRepository,
    FakeTriageRepository,
    FakeUserRepository,
    FakeWellbeingRepository,
    ScriptedLlmProvider,
)

RAW = """Изометрия квадрицепса 3 подхода по 10, держать 5 секунд
Подъём прямой ноги 3х12
Нельзя бегать и прыгать 3 недели"""


class Harness:
    def __init__(self, registry: ScenarioRegistry, provider: ScriptedLlmProvider) -> None:
        self.users = FakeUserRepository()
        self.sessions = FakeSessionRepository()
        self.plans = FakePlanRepository(self.sessions)
        self.checkins = FakeCheckinRepository()
        self.triage = FakeTriageRepository()
        self.events = FakeEventRepository()
        self.audit = FakeLlmCallRepository()
        self.items = FakePlanItemRepository()
        self.wellbeing = FakeWellbeingRepository()
        self.registry = registry
        # enabled_tasks задаём явно: иначе тест зависит от .env разработчика.
        self.settings = LlmSettings(
            provider="scripted",
            api_key="x",
            enabled_tasks=["parse_prescription"],
        )
        self.runner = LlmRunner(provider, self.settings, self.audit)
        self.tracker = TrackerService(
            plans=self.plans,
            checkins=self.checkins,
            sessions=self.sessions,
            triage=self.triage,
            events=self.events,
            library=load_library(),
        )
        self.daily = DailyPlanService(self.items, self.wellbeing, self.sessions, self.events)

    async def session(self):
        user = await self.users.create(tg_id=1, username="t", locale="ru")
        session = await self.sessions.create(user_id=user.id, sport=Sport.FOOTBALL)
        session.scenario_id = "football.ankle_sprain"
        await self.sessions.update(session)
        return session


@pytest.fixture
def scripted(registry: ScenarioRegistry) -> Harness:
    return Harness(
        registry,
        ScriptedLlmProvider(
            {
                "parse_prescription": {
                    "items": [
                        "Изометрия квадрицепса 3 подхода по 10, держать 5 секунд",
                        "Подъём прямой ноги 3х12",
                    ],
                    "limits": ["Нельзя бегать и прыгать 3 недели"],
                    "duration_days": 21,
                }
            }
        ),
    )


@pytest.fixture
def broken(registry: ScenarioRegistry) -> Harness:
    return Harness(registry, ScriptedLlmProvider(fail=True))


class TestParsing:
    async def test_items_and_limits_are_verbatim(self, scripted: Harness) -> None:
        session = await scripted.session()
        parsed = await parse_prescription(scripted.runner, RAW, session_id=session.id)
        assert parsed.items[0].startswith("Изометрия квадрицепса 3 подхода по 10")
        assert parsed.limits == ("Нельзя бегать и прыгать 3 недели",)
        assert parsed.duration_days == 21
        assert not parsed.from_fallback

    async def test_fallback_splits_by_lines(self, broken: Harness) -> None:
        """Модель недоступна — текст пользователя сохраняется как есть, не теряется."""
        session = await broken.session()
        parsed = await parse_prescription(broken.runner, RAW, session_id=session.id)
        assert parsed.from_fallback
        assert len(parsed.items) == 3
        assert "3 подхода по 10" in parsed.items[0]

    async def test_empty_text(self, broken: Harness) -> None:
        parsed = await parse_prescription(broken.runner, "   ")
        assert parsed.is_empty

    def test_split_drops_bullets_and_short_noise(self) -> None:
        parsed = split_plainly("- Ходьба 20 минут\n\n•\nПриседания 3х10\nок")
        assert parsed.items == ("Ходьба 20 минут", "Приседания 3х10")


class TestPlanFromPrescription:
    async def test_plan_is_marked_as_prescription(self, scripted: Harness) -> None:
        session = await scripted.session()
        scenario = scripted.registry.require("football.ankle_sprain")
        plan, _ = await scripted.tracker.start_prescription_plan(
            session,
            scenario,
            items=["Изометрия квадрицепса 3х10"],
            limits=["Без бега"],
            duration_days=21,
        )
        assert plan.source is PlanSource.PRESCRIPTION
        assert EventType.PLAN_STARTED in scripted.events.types()

    async def test_wording_is_preserved_and_no_library_exercises(self, scripted: Harness) -> None:
        """Наши упражнения не должны подменить назначенную нагрузку."""
        session = await scripted.session()
        scenario = scripted.registry.require("football.ankle_sprain")
        plan, _ = await scripted.tracker.start_prescription_plan(
            session,
            scenario,
            items=["Изометрия квадрицепса 3 подхода по 10, держать 5 секунд"],
            limits=["Нельзя бегать 3 недели"],
        )

        assert exercises_from_snapshot(plan.plan_snapshot) == {}

        view = await scripted.daily.today(plan)
        assert all(item.kind is ItemKind.TASK for item in view.items)
        texts = [item.title for item in view.items]
        assert "Изометрия квадрицепса 3 подхода по 10, держать 5 секунд" in texts
        assert any("Ограничение: Нельзя бегать 3 недели" == t for t in texts)

    async def test_duration_is_bounded(self, scripted: Harness) -> None:
        session = await scripted.session()
        scenario = scripted.registry.require("football.ankle_sprain")
        plan, _ = await scripted.tracker.start_prescription_plan(
            session, scenario, items=["Ходьба"], duration_days=500
        )
        assert scripted.tracker.plan_of(plan).stages[0].days == 90

    async def test_default_duration_when_not_given(self, scripted: Harness) -> None:
        session = await scripted.session()
        scenario = scripted.registry.require("football.ankle_sprain")
        plan, _ = await scripted.tracker.start_prescription_plan(
            session, scenario, items=["Ходьба"], duration_days=None
        )
        assert scripted.tracker.plan_of(plan).stages[0].days == 14

    async def test_morning_check_is_always_added(self, scripted: Harness) -> None:
        session = await scripted.session()
        scenario = scripted.registry.require("football.ankle_sprain")
        plan, _ = await scripted.tracker.start_prescription_plan(
            session, scenario, items=["Ходьба"]
        )
        keys = [task.key for task in scripted.tracker.plan_of(plan).stages[0].tasks]
        assert "morning_check" in keys
