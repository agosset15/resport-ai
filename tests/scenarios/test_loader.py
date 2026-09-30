from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.domain.enums import Sport
from core.domain.scenario import ScenarioRegistry
from core.scenarios.loader import (
    ScenarioValidationError,
    load_registry,
    load_scenario_file,
)

BASE = Path(__file__).resolve().parents[1] / "fixtures" / "defs"
VALID = BASE / "football" / "ankle_sprain.yaml"


def _write(tmp_path: Path, mutate) -> Path:
    raw = yaml.safe_load(VALID.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


class TestHappyPath:
    def test_registry_has_both_sports(self, registry: ScenarioRegistry) -> None:
        assert set(registry.ids()) == {"football.ankle_sprain", "basketball.patellar_pain"}
        assert len(registry.for_sport(Sport.FOOTBALL)) == 1
        assert len(registry.for_sport(Sport.BASKETBALL)) == 1

    def test_options_get_labels(self, registry: ScenarioRegistry) -> None:
        question = registry.require("football.ankle_sprain").question("q_weightbearing")
        assert question is not None
        assert question.option("cannot") is not None
        assert question.option("cannot").label == "Нет, наступать не могу"  # type: ignore[union-attr]

    def test_default_rule_is_last(self, registry: ScenarioRegistry) -> None:
        for scenario in registry.scenarios.values():
            assert scenario.routing[-1].is_default


class TestValidation:
    def test_unknown_question_in_red_flag(self, tmp_path: Path) -> None:
        def mutate(raw: dict) -> None:
            raw["red_flags"][0]["question"] = "q_nonexistent"

        with pytest.raises(ScenarioValidationError, match="неизвестный вопрос"):
            load_scenario_file(_write(tmp_path, mutate))

    def test_unknown_option_in_red_flag(self, tmp_path: Path) -> None:
        def mutate(raw: dict) -> None:
            raw["red_flags"][0]["when"] = {"equals": "totally_broken"}

        with pytest.raises(ScenarioValidationError, match="нет опций"):
            load_scenario_file(_write(tmp_path, mutate))

    def test_missing_default_rule(self, tmp_path: Path) -> None:
        def mutate(raw: dict) -> None:
            raw["routing"] = [r for r in raw["routing"] if "default" not in r]

        with pytest.raises(ScenarioValidationError, match="нет default-правила"):
            load_scenario_file(_write(tmp_path, mutate))

    def test_routing_plan_must_exist(self, tmp_path: Path) -> None:
        def mutate(raw: dict) -> None:
            for rule in raw["routing"]:
                if rule.get("plan"):
                    rule["plan"] = "ghost_plan"

        with pytest.raises(ScenarioValidationError, match="не описан в plans"):
            load_scenario_file(_write(tmp_path, mutate))

    def test_sport_prefix_enforced(self, tmp_path: Path) -> None:
        def mutate(raw: dict) -> None:
            raw["id"] = "basketball.ankle_sprain"

        with pytest.raises(ScenarioValidationError, match="должен начинаться"):
            load_scenario_file(_write(tmp_path, mutate))

    def test_schema_rejects_unknown_field(self, tmp_path: Path) -> None:
        def mutate(raw: dict) -> None:
            raw["magic"] = True

        with pytest.raises(ScenarioValidationError):
            load_scenario_file(_write(tmp_path, mutate))

    def test_empty_advance_if_rejected(self, tmp_path: Path) -> None:
        def mutate(raw: dict) -> None:
            plan = next(iter(raw["plans"].values()))
            plan["stages"][0]["advance_if"] = {"consecutive": 1}

        with pytest.raises(ScenarioValidationError, match="advance_if пуст"):
            load_scenario_file(_write(tmp_path, mutate))

    def test_ask_if_cannot_reference_later_question(self, tmp_path: Path) -> None:
        def mutate(raw: dict) -> None:
            raw["questions"][0]["ask_if"] = {"q_swelling": "severe"}

        with pytest.raises(ScenarioValidationError, match="задаётся позже"):
            load_scenario_file(_write(tmp_path, mutate))

    def test_empty_dir_fails(self, tmp_path: Path) -> None:
        with pytest.raises(ScenarioValidationError, match="нет ни одного сценария"):
            load_registry(tmp_path)


class TestProductionDefs:
    """Боевые YAML не участвуют в логических тестах, но обязаны грузиться и валидироваться."""

    def test_all_scenarios_load(self) -> None:
        from tests.conftest import PROD_DEFS_DIR

        prod = load_registry(PROD_DEFS_DIR)
        assert prod.ids()
        for scenario in prod.scenarios.values():
            assert scenario.id.startswith(f"{scenario.sport.value}.")
            assert scenario.routing[-1].is_default
