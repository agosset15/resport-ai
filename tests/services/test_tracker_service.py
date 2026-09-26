from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.domain.enums import (
    EventType,
    Feeling,
    Outcome,
    PlanStatus,
    SessionStatus,
    Sport,
)
from core.domain.scenario import Scenario
from core.scenarios.plan_engine import TrackerAction
from core.services.tracker import TrackerService
from tests.fakes import (
    FakeCheckinRepository,
    FakeEventRepository,
    FakePlanRepository,
    FakeSessionRepository,
    FakeTriageRepository,
    FakeUserRepository,
)

START = date(2026, 3, 2)


class Harness:
    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.sessions = FakeSessionRepository()
        self.plans = FakePlanRepository(self.sessions)
        self.checkins = FakeCheckinRepository()
        self.triage = FakeTriageRepository()
        self.events = FakeEventRepository()
        self.service = TrackerService(
            plans=self.plans,
            checkins=self.checkins,
            sessions=self.sessions,
            triage=self.triage,
            events=self.events,
        )


@pytest.fixture
async def started(ankle: Scenario):
    harness = Harness()
    user = await harness.users.create(tg_id=7, username="a", locale="ru")
    session = await harness.sessions.create(user.id, Sport.FOOTBALL)
    session.scenario_id = ankle.id
    session.scenario_version = ankle.version
    plan, _ = await harness.service.start_plan(session, ankle, "ankle_sprain_basic")
    return harness, session, plan


class TestStart:
    async def test_snapshot_written(self, started, ankle: Scenario) -> None:
        harness, session, plan = started
        assert plan.plan_snapshot["scenario_version"] == ankle.version
        assert plan.plan_snapshot["plan_key"] == "ankle_sprain_basic"
        assert len(plan.plan_snapshot["stages"]) == 3
        assert harness.sessions.sessions[session.id].status is SessionStatus.PLAN_ACTIVE
        assert EventType.PLAN_STARTED in harness.events.types()

    async def test_plan_survives_scenario_change(self, started) -> None:
        """Правка YAML не трогает уже выданный план: читаем из снимка."""
        harness, _, plan = started
        plan.plan_snapshot["stages"][0]["title"] = "Старое название"
        view = harness.service.stage_view(plan)
        assert view.stage_title == "Старое название"

    async def test_first_stage_view(self, started) -> None:
        harness, _, plan = started
        view = harness.service.stage_view(plan)
        assert view.stage_index == 0
        assert view.stage_total == 3
        assert view.day_number == 1
        assert [t.key for t in view.tasks] == ["ice", "elevation", "compression", "rest"]


class TestCheckins:
    async def test_stay_when_one_checkin(self, started) -> None:
        harness, _, plan = started
        result = await harness.service.submit_checkin(
            plan, feeling=Feeling.BETTER, tasks_done=["ice"], day=START
        )
        assert result.action is TrackerAction.STAY
        assert harness.checkins.items[0].stage_index == 0
        assert EventType.CHECKIN_SUBMITTED in harness.events.types()

    async def test_advance_after_two_good_days(self, started) -> None:
        harness, _, plan = started
        await harness.service.submit_checkin(
            plan, feeling=Feeling.BETTER, tasks_done=["ice"], day=START
        )
        result = await harness.service.submit_checkin(
            plan, feeling=Feeling.SAME, tasks_done=["ice"], day=START + timedelta(days=1)
        )
        assert result.action is TrackerAction.ADVANCE
        assert harness.plans.plans[plan.id].current_stage == 1
        assert EventType.STAGE_ADVANCED in harness.events.types()

    async def test_second_checkin_same_day_ignored(self, started) -> None:
        harness, _, plan = started
        await harness.service.submit_checkin(plan, feeling=Feeling.BETTER, tasks_done=[], day=START)
        await harness.service.submit_checkin(plan, feeling=Feeling.WORSE, tasks_done=[], day=START)
        assert len(harness.checkins.items) == 1

    async def test_today_view_marks_done(self, started) -> None:
        harness, _, plan = started
        await harness.service.submit_checkin(
            plan, feeling=Feeling.BETTER, tasks_done=["ice", "rest"], timezone="Europe/Moscow"
        )
        view = await harness.service.today_view(plan, timezone="Europe/Moscow")
        assert view.checkin_done_today
        assert set(view.done_today) == {"ice", "rest"}

    async def test_today_is_local_not_utc(self, started) -> None:
        """Чек-ин ночью по локальному времени не должен попадать во вчерашний день UTC."""
        harness, _, plan = started
        await harness.service.submit_checkin(
            plan, feeling=Feeling.BETTER, tasks_done=[], timezone="Asia/Vladivostok"
        )
        stored = harness.checkins.items[0].date
        assert stored == datetime.now(ZoneInfo("Asia/Vladivostok")).date()
        local_view = await harness.service.today_view(plan, timezone="Asia/Vladivostok")
        assert local_view.checkin_done_today


class TestEscalation:
    async def test_two_worse_escalates(self, started) -> None:
        harness, session, plan = started
        await harness.service.submit_checkin(plan, feeling=Feeling.WORSE, tasks_done=[], day=START)
        result = await harness.service.submit_checkin(
            plan, feeling=Feeling.WORSE, tasks_done=[], day=START + timedelta(days=1)
        )
        assert result.action is TrackerAction.ESCALATE
        assert result.escalated
        assert harness.plans.plans[plan.id].status is PlanStatus.ESCALATED
        assert harness.sessions.sessions[session.id].status is SessionStatus.REFERRED
        assert EventType.PLAN_ESCALATED in harness.events.types()

    async def test_escalation_writes_triage_result(self, started) -> None:
        harness, session, plan = started
        await harness.service.submit_checkin(plan, feeling=Feeling.WORSE, tasks_done=[], day=START)
        await harness.service.submit_checkin(
            plan, feeling=Feeling.WORSE, tasks_done=[], day=START + timedelta(days=1)
        )
        stored = harness.triage.results[session.id]
        assert stored.outcome is Outcome.REFER_SPECIALIST
        assert "tracker_escalation" in stored.reason_codes

    async def test_single_worse_does_not_escalate(self, started) -> None:
        harness, _, plan = started
        result = await harness.service.submit_checkin(
            plan, feeling=Feeling.WORSE, tasks_done=[], day=START
        )
        assert result.action is TrackerAction.STAY

    async def test_worse_streak_broken_by_better(self, started) -> None:
        harness, _, plan = started
        await harness.service.submit_checkin(plan, feeling=Feeling.WORSE, tasks_done=[], day=START)
        await harness.service.submit_checkin(
            plan, feeling=Feeling.BETTER, tasks_done=[], day=START + timedelta(days=1)
        )
        result = await harness.service.submit_checkin(
            plan, feeling=Feeling.WORSE, tasks_done=[], day=START + timedelta(days=2)
        )
        assert result.action is TrackerAction.STAY


class TestCompletion:
    async def test_full_plan_completes(self, started) -> None:
        harness, session, plan = started
        day = START
        tasks = ["ice", "elevation", "compression", "rest"]

        for _ in range(12):
            current = harness.plans.plans[plan.id]
            if current.status is not PlanStatus.ACTIVE:
                break
            result = await harness.service.submit_checkin(
                current, feeling=Feeling.BETTER, tasks_done=tasks, day=day
            )
            day += timedelta(days=1)
            if result.completed:
                break

        assert harness.plans.plans[plan.id].status is PlanStatus.COMPLETED
        assert harness.sessions.sessions[session.id].status is SessionStatus.COMPLETED
        assert EventType.PLAN_COMPLETED in harness.events.types()
