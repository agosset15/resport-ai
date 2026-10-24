"""Библиотека упражнений: загрузка, валидация и связь со сценариями.

Главное требование ТЗ: бот не придумывает дозировки — значит они обязаны быть в данных,
а ссылка на несуществующее упражнение должна ронять старт, а не всплывать в плане.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.domain.exercise import BODY_REGIONS, PHASES, Dosage
from core.scenarios.exercises import ExerciseValidationError, load_library
from core.scenarios.loader import ScenarioValidationError, load_registry
from tests.conftest import PROD_DEFS_DIR


@pytest.fixture(scope="module")
def library():
    return load_library()


def write_library(tmp_path: Path, exercises: list[dict]) -> Path:
    path = tmp_path / "exercises.yaml"
    path.write_text(
        yaml.safe_dump({"version": 1, "exercises": exercises}, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def minimal(**overrides) -> dict:
    base = {
        "id": "demo",
        "title": "Демо",
        "instruction": "Инструкция",
        "dosage": {"sets": 2, "reps": 10},
        "body_region": "knee",
        "phase": "acute",
        "limits": ["Без боли"],
    }
    base.update(overrides)
    return base


class TestLoading:
    def test_production_library_loads(self, library) -> None:
        assert library.ids()

    def test_every_exercise_has_limits_and_dosage(self, library) -> None:
        for exercise in library.exercises.values():
            assert exercise.limits, exercise.id
            dosage = exercise.dosage
            assert dosage.reps or dosage.duration_seconds or dosage.note, exercise.id

    def test_regions_and_phases_are_known(self, library) -> None:
        for exercise in library.exercises.values():
            assert exercise.body_region in BODY_REGIONS, exercise.id
            assert exercise.phase in PHASES, exercise.id

    def test_every_region_has_exercises(self, library) -> None:
        for region in BODY_REGIONS:
            if region == "general":
                continue
            assert library.for_region(region), region

    def test_content_is_still_draft(self, library) -> None:
        """Содержание не подписано врачом — отчёт о ревью должен это показывать."""
        assert library.drafts()


class TestValidation:
    def test_duplicate_ids_rejected(self, tmp_path: Path) -> None:
        path = write_library(tmp_path, [minimal(), minimal()])
        with pytest.raises(ExerciseValidationError, match="дублирующиеся id"):
            load_library(path)

    def test_missing_limits_rejected(self, tmp_path: Path) -> None:
        path = write_library(tmp_path, [minimal(limits=[])])
        with pytest.raises(ExerciseValidationError, match="limits"):
            load_library(path)

    def test_empty_dosage_rejected(self, tmp_path: Path) -> None:
        path = write_library(tmp_path, [minimal(dosage={"sets": 3})])
        with pytest.raises(ExerciseValidationError, match="dosage"):
            load_library(path)

    def test_both_reps_and_duration_rejected(self, tmp_path: Path) -> None:
        path = write_library(tmp_path, [minimal(dosage={"reps": 10, "duration_seconds": 30})])
        with pytest.raises(ExerciseValidationError, match="выбери одно"):
            load_library(path)

    def test_unknown_region_rejected_by_schema(self, tmp_path: Path) -> None:
        path = write_library(tmp_path, [minimal(body_region="elbow")])
        with pytest.raises(ExerciseValidationError):
            load_library(path)


class TestScenarioLinks:
    def test_production_scenarios_reference_existing_exercises(self, library) -> None:
        registry = load_registry(PROD_DEFS_DIR, library)
        referenced = {
            exercise_id
            for scenario in registry.scenarios.values()
            for plan in scenario.plans.values()
            for stage in plan.stages
            for exercise_id in stage.exercises
        }
        assert referenced, "сценарии не ссылаются ни на одно упражнение"
        assert referenced <= set(library.ids())

    def test_unknown_exercise_breaks_the_loader(self, tmp_path: Path, library) -> None:
        """Опечатка в id не должна тихо превращаться в пустой этап."""
        source = (PROD_DEFS_DIR / "football" / "football.ankle_sprain.yaml").read_text(
            encoding="utf-8"
        )
        broken = source.replace("exercises: [ankle_pumps", "exercises: [no_such_exercise")
        assert broken != source

        defs = tmp_path / "football"
        defs.mkdir()
        (defs / "football.ankle_sprain.yaml").write_text(broken, encoding="utf-8")
        with pytest.raises(ScenarioValidationError, match="нет таких упражнений"):
            load_registry(tmp_path, library)

    def test_self_rehab_plans_have_exercises(self, library) -> None:
        registry = load_registry(PROD_DEFS_DIR, library)
        for scenario in registry.scenarios.values():
            for key, plan in scenario.plans.items():
                if not key.startswith("self_rehab"):
                    continue
                assert any(stage.exercises for stage in plan.stages), f"{scenario.id}/{key}"

    def test_exercises_match_scenario_region(self, library) -> None:
        """Упражнение для пальца не должно попасть в сценарий голеностопа."""
        registry = load_registry(PROD_DEFS_DIR, library)
        for scenario in registry.scenarios.values():
            if scenario.body_region is None:
                continue
            for plan in scenario.plans.values():
                for stage in plan.stages:
                    for exercise_id in stage.exercises:
                        exercise = library.require(exercise_id)
                        assert exercise.body_region in (
                            scenario.body_region,
                            "general",
                        ), f"{scenario.id}: {exercise_id} для {exercise.body_region}"


class TestDosageText:
    @pytest.mark.parametrize(
        ("dosage", "expected"),
        [
            (Dosage(sets=3, reps=12), "3 подхода по 12 повторений"),
            (Dosage(reps=1), "1 повторение"),
            (Dosage(sets=5, reps=2), "5 подходов по 2 повторения"),
            (Dosage(duration_seconds=600), "10 минут"),
            (Dosage(duration_seconds=30), "30 секунд"),
            (Dosage(sets=3, duration_seconds=30), "3 подхода по 30 секунд"),
            (Dosage(note="по самочувствию врача"), "по самочувствию врача"),
            (Dosage(), "по самочувствию"),
        ],
    )
    def test_human_readable(self, dosage: Dosage, expected: str) -> None:
        assert dosage.human() == expected

    def test_note_is_appended(self) -> None:
        assert Dosage(sets=2, reps=10, note="медленно").human() == (
            "2 подхода по 10 повторений — медленно"
        )

    def test_lookup_hint_falls_back_to_title(self, library) -> None:
        exercise = library.require("glute_bridge")
        assert "Подъём таза лёжа" in exercise.lookup_text()
