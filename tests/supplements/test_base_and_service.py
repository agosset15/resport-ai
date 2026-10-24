"""База БАДов, анкета и сервис: валидация, журнал приёма, нежелательные реакции."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

from core.domain.entities import RecoveryPlan, User
from core.domain.enums import (
    EventType,
    ItemKind,
    ItemStatus,
    ReactionSeverity,
    SupplementStatus,
)
from core.domain.supplement import UNFILLED, SupplementRegistry
from core.services.supplements import SupplementService, classify_severity
from core.supplements.intake_form import QUESTIONS, SupplementProfile, parse_list
from core.supplements.loader import SupplementValidationError, load_supplements
from tests.fakes import (
    FakeAdverseReactionRepository,
    FakeEventRepository,
    FakePlanItemRepository,
    FakeSupplementIntakeRepository,
    FakeSupplementProfileRepository,
)
from tests.supplements.test_matcher import registry, supplement

TODAY = date(2026, 10, 24)


def write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / f"{data['id']}.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return tmp_path


def minimal(**overrides) -> dict:
    base = {
        "id": "demo",
        "product": "Продукт",
        "manufacturer": "Производитель",
        "composition": [{"name": "Магний", "amount": "300", "unit": "мг"}],
        "rationale": "Основание",
        "benefit_limits": "Пределы пользы",
        "intake": {"dose_text": "1 капсула в день", "duration_text": "4 недели"},
        "contraindications": ["Болезни почек"],
        "adverse_reaction_actions": "Прекратить приём и обратиться за помощью",
        "source": {
            "title": "Этикетка",
            "url": "https://example.test/label",
            "retrieved_at": "2026-10-24",
        },
        "updated_at": "2026-10-24",
        "review_status": "approved",
    }
    base.update(overrides)
    return base


class TestProductionBase:
    def test_demo_base_loads(self) -> None:
        reg = load_supplements()
        assert reg.ids()

    def test_demo_base_recommends_nothing_yet(self) -> None:
        """Демо-записи не подписаны и без дозировок — подбор обязан молчать."""
        reg = load_supplements()
        assert reg.recommendable() == ()
        assert len(reg.drafts()) == len(reg.ids())

    def test_every_entry_cites_a_source_and_date(self) -> None:
        for item in load_supplements().supplements.values():
            assert item.source.url.startswith("http"), item.id
            assert item.source.retrieved_at, item.id
            assert item.updated_at, item.id

    def test_min_age_is_adult(self) -> None:
        for item in load_supplements().supplements.values():
            assert item.min_age >= 18, item.id


class TestValidation:
    def test_approved_without_dosage_is_rejected(self, tmp_path: Path) -> None:
        """Главный запрет: подписать запись без дозировки нельзя."""
        data = minimal(intake={"dose_text": UNFILLED, "duration_text": "4 недели"})
        with pytest.raises(SupplementValidationError, match="не придумывает дозировки"):
            load_supplements(write(tmp_path, data))

    def test_approved_without_contraindications_is_rejected(self, tmp_path: Path) -> None:
        data = minimal(contraindications=[])
        with pytest.raises(SupplementValidationError, match="противопоказания"):
            load_supplements(write(tmp_path, data))

    def test_approved_without_reaction_actions_is_rejected(self, tmp_path: Path) -> None:
        data = minimal(adverse_reaction_actions="")
        with pytest.raises(SupplementValidationError):
            load_supplements(write(tmp_path, data))

    def test_draft_may_be_incomplete(self, tmp_path: Path) -> None:
        data = minimal(
            review_status="draft",
            intake={"dose_text": UNFILLED, "duration_text": UNFILLED},
            contraindications=[],
        )
        reg = load_supplements(write(tmp_path, data))
        assert reg.require("demo").needs_review

    def test_min_age_below_adult_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(SupplementValidationError):
            load_supplements(write(tmp_path, minimal(min_age=16)))

    def test_missing_source_is_rejected_by_schema(self, tmp_path: Path) -> None:
        data = minimal()
        data.pop("source")
        with pytest.raises(SupplementValidationError):
            load_supplements(write(tmp_path, data))

    def test_duplicate_component_is_rejected(self, tmp_path: Path) -> None:
        data = minimal(composition=[{"name": "Магний"}, {"name": "магний"}])
        with pytest.raises(SupplementValidationError, match="дважды"):
            load_supplements(write(tmp_path, data))

    def test_empty_directory_is_valid(self, tmp_path: Path) -> None:
        """Пустая база — рабочее состояние, а не ошибка запуска."""
        assert load_supplements(tmp_path).ids() == ()


class TestIntakeForm:
    def test_age_is_asked_first(self) -> None:
        assert QUESTIONS[0].key.value == "age"

    def test_all_required_topics_are_covered(self) -> None:
        keys = {question.key.value for question in QUESTIONS}
        assert keys == {
            "age",
            "allergies",
            "conditions",
            "medications",
            "other_supplements",
            "pregnant",
            "breastfeeding",
            "upcoming_surgery",
        }

    @pytest.mark.parametrize("raw", ["нет", "НЕТ", "-", "ничего"])
    def test_no_means_empty_list(self, raw: str) -> None:
        assert parse_list(raw) == ()

    def test_list_is_split(self) -> None:
        assert parse_list("рыба, орехи; лактоза") == ("рыба", "орехи", "лактоза")

    def test_round_trip_through_answers(self) -> None:
        profile = SupplementProfile(
            age=30,
            allergies=("рыба",),
            medications=(),
            pregnant=False,
            breastfeeding=False,
            upcoming_surgery=False,
        )
        restored = SupplementProfile.from_answers(profile.to_answers())
        assert restored.age == 30
        assert restored.allergies == ("рыба",)
        assert restored.is_complete

    def test_missing_answers_make_profile_incomplete(self) -> None:
        assert not SupplementProfile.from_answers({"age": 30}).is_complete


class TestSeverity:
    @pytest.mark.parametrize(
        "text",
        [
            "трудно дышать",
            "отёк лица",
            "сыпь по всему телу",
            "потерял сознание",
            "сильно колотится сердце",
        ],
    )
    def test_severe_markers(self, text: str) -> None:
        assert classify_severity(text) is ReactionSeverity.SEVERE

    @pytest.mark.parametrize("text", ["немного тошнит", "горький привкус"])
    def test_mild_by_default(self, text: str) -> None:
        assert classify_severity(text) is ReactionSeverity.MILD


class Harness:
    def __init__(self, reg: SupplementRegistry) -> None:
        self.profiles = FakeSupplementProfileRepository()
        self.intakes = FakeSupplementIntakeRepository()
        self.reactions = FakeAdverseReactionRepository()
        self.items = FakePlanItemRepository()
        self.events = FakeEventRepository()
        self.service = SupplementService(
            reg, self.profiles, self.intakes, self.reactions, self.items, self.events
        )


@pytest.fixture
def harness() -> Harness:
    return Harness(registry(supplement("magnesium"), supplement("omega", components=("ЭПК",))))


@pytest.fixture
def user() -> User:
    return User(id=uuid4(), tg_id=1, username="t")


@pytest.fixture
def plan() -> RecoveryPlan:
    return RecoveryPlan(
        id=uuid4(),
        session_id=uuid4(),
        plan_key="p",
        plan_snapshot={},
        started_at=datetime(2026, 10, 24, tzinfo=UTC),
    )


class TestService:
    async def test_no_profile_means_no_selection(self, harness: Harness, user: User) -> None:
        assert await harness.service.selection(user) is None

    async def test_profile_is_saved_and_used(self, harness: Harness, user: User) -> None:
        profile = SupplementProfile(
            age=30, pregnant=False, breastfeeding=False, upcoming_surgery=False
        )
        await harness.service.save_profile(user, profile)
        assert EventType.SUPPLEMENT_PROFILE_SAVED in harness.events.types()

        selection = await harness.service.selection(user)
        assert selection is not None
        assert len(selection.recommended) == 2
        assert EventType.SUPPLEMENT_OFFERED in harness.events.types()

    async def test_suspension_is_recorded(self, harness: Harness, user: User) -> None:
        await harness.service.save_profile(
            user,
            SupplementProfile(
                age=30,
                medications=("варфарин",),
                pregnant=False,
                breastfeeding=False,
                upcoming_surgery=False,
            ),
        )
        selection = await harness.service.selection(user)
        assert selection is not None
        assert selection.is_suspended
        assert EventType.SUPPLEMENT_SELECTION_SUSPENDED in harness.events.types()

    async def test_add_and_decline(self, harness: Harness, user: User) -> None:
        item = harness.service._registry.require("magnesium")
        await harness.service.add_to_plan(user, item)
        assert [s.id for s in await harness.service.active_supplements(user)] == ["magnesium"]

        await harness.service.decline(user, item)
        assert await harness.service.active_supplements(user) == ()
        types = harness.events.types()
        assert EventType.SUPPLEMENT_ADDED in types
        assert EventType.SUPPLEMENT_DECLINED in types

    async def test_taking_one_blocks_duplicate_component(
        self, harness: Harness, user: User
    ) -> None:
        await harness.service.save_profile(
            user,
            SupplementProfile(age=30, pregnant=False, breastfeeding=False, upcoming_surgery=False),
        )
        await harness.service.add_to_plan(user, harness.service._registry.require("magnesium"))
        selection = await harness.service.selection(user)
        assert selection is not None
        assert [s.id for s in selection.recommended] == ["omega"]

    async def test_intake_marks_do_not_count_toward_programme(
        self, harness: Harness, user: User, plan: RecoveryPlan
    ) -> None:
        """Отметка приёма пишется как ItemKind.SUPPLEMENT и в процент не входит."""
        from core.services.progress import COUNTED_KINDS, day_mark

        await harness.service.mark_taken(plan, "magnesium", taken=True, day=TODAY)
        logs = await harness.items.for_date(plan.id, TODAY)
        assert [log.item_kind for log in logs] == [ItemKind.SUPPLEMENT]
        assert logs[0].status is ItemStatus.DONE

        assert ItemKind.SUPPLEMENT not in COUNTED_KINDS
        assert day_mark(logs).value == "no_data"

    async def test_reaction_stops_the_course(self, harness: Harness, user: User) -> None:
        await harness.service.add_to_plan(user, harness.service._registry.require("magnesium"))
        severity = await harness.service.report_reaction(
            user, "magnesium", "начало тошнить через час"
        )

        assert severity is ReactionSeverity.MILD
        assert await harness.service.active_supplements(user) == ()
        stored = await harness.intakes.for_user(user.id)
        assert stored[0].status is SupplementStatus.STOPPED
        assert len(await harness.service.reactions_of(user.id)) == 1
        assert EventType.ADVERSE_REACTION_REPORTED in harness.events.types()

    async def test_severe_reaction_is_classified(self, harness: Harness, user: User) -> None:
        severity = await harness.service.report_reaction(user, "magnesium", "стало трудно дышать")
        assert severity is ReactionSeverity.SEVERE
