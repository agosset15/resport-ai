from __future__ import annotations

from pathlib import Path

import pytest

from core.domain.scenario import Scenario, ScenarioRegistry
from core.scenarios.engine import ScenarioEngine
from core.scenarios.loader import load_registry

DEFS_DIR = Path(__file__).resolve().parent.parent / "core" / "scenarios" / "defs"


@pytest.fixture(scope="session")
def registry() -> ScenarioRegistry:
    return load_registry(DEFS_DIR)


@pytest.fixture(scope="session")
def ankle(registry: ScenarioRegistry) -> Scenario:
    return registry.require("football.ankle_sprain")


@pytest.fixture(scope="session")
def knee(registry: ScenarioRegistry) -> Scenario:
    return registry.require("basketball.patellar_pain")


@pytest.fixture
def ankle_engine(ankle: Scenario) -> ScenarioEngine:
    return ScenarioEngine(ankle)


@pytest.fixture
def knee_engine(knee: Scenario) -> ScenarioEngine:
    return ScenarioEngine(knee)
