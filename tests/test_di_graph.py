"""Граф зависимостей должен собираться. Без этого бот падает на старте.

Этот тест появился после реальной поломки: у `ReportService` зависимости были
объявлены как `SupplementRegistry | None`, и Dishka не нашла фабрику для Optional-типа.
Юнит-тесты сервиса проходили, потому что собирали его напрямую, минуя DI, —
и контейнер падал только в рантайме.

Проверка намеренно не требует ни Postgres, ни Redis: Dishka валидирует граф при
сборке контейнера, не создавая объекты.
"""

from __future__ import annotations

import pytest
from dishka import AsyncContainer

from apps.di import build_container
from core.domain.exercise import ExerciseLibrary
from core.domain.scenario import ScenarioRegistry
from core.domain.supplement import SupplementRegistry


@pytest.fixture
async def container():
    created: AsyncContainer = build_container()
    yield created
    await created.close()


class TestGraph:
    def test_container_builds(self) -> None:
        """Любая незакрытая зависимость в любом сервисе ломает это немедленно."""
        build_container()

    async def test_app_scope_resolves(self, container: AsyncContainer) -> None:
        """Первое разрешение прогоняет валидацию всего графа, включая REQUEST-скоуп."""
        assert (await container.get(ScenarioRegistry)).ids()
        assert (await container.get(ExerciseLibrary)).ids()
        await container.get(SupplementRegistry)

    async def test_registries_are_consistent(self, container: AsyncContainer) -> None:
        """Сценарии ссылаются только на существующие упражнения — проверяется на старте."""
        registry = await container.get(ScenarioRegistry)
        library = await container.get(ExerciseLibrary)
        referenced = {
            exercise_id
            for scenario in registry.scenarios.values()
            for plan in scenario.plans.values()
            for stage in plan.stages
            for exercise_id in stage.exercises
        }
        assert referenced <= set(library.ids())


class TestRouters:
    def test_dispatcher_builds_with_all_routers(self) -> None:
        from apps.bot.factory import build_dispatcher

        dispatcher = build_dispatcher(build_container())
        names = [router.name for router in dispatcher.sub_routers]

        assert "errors" == names[-1], "обработчик ошибок должен быть последним"
        assert names.index("pain_point") < names.index("triage"), (
            "PainPointCB должен разбираться до общего фильтра AnswerCB"
        )
        assert len(names) == len(set(names)), "роутер подключён дважды"
