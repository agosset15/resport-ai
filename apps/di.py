"""Композиционный корень. Единственное место, где core встречается с infra."""

from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import AsyncContainer, Provider, Scope, make_async_container, provide
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from core.config import (
    AppSettings,
    BotSettings,
    ContentSettings,
    DatabaseSettings,
    LlmSettings,
    RedisSettings,
    Settings,
    get_settings,
)
from core.domain.scenario import ScenarioRegistry
from core.llm.provider import LlmProvider
from core.llm.runner import LlmCache, LlmRunner
from core.scenarios.loader import load_registry
from core.services.export import ExportService
from core.services.protocols import (
    CheckinRepository,
    EventRepository,
    LlmCallRepository,
    PlanRepository,
    SessionRepository,
    TriageRepository,
    UserRepository,
)
from core.services.tracker import TrackerService
from core.services.triage import TriageService
from core.services.user import UserService
from infra.cache.llm_cache import RedisLlmCache
from infra.cache.redis import build_redis
from infra.db.engine import build_engine, build_session_factory
from infra.db.repositories.audit import SqlEventRepository, SqlLlmCallRepository
from infra.db.repositories.export import SqlExportRepository
from infra.db.repositories.plans import SqlCheckinRepository, SqlPlanRepository
from infra.db.repositories.sessions import SqlSessionRepository
from infra.db.repositories.triage import SqlTriageRepository
from infra.db.repositories.users import SqlUserRepository
from infra.llm.clients import build_provider


class SettingsProvider(Provider):
    scope = Scope.APP

    @provide
    def settings(self) -> Settings:
        return get_settings()

    @provide
    def app(self, settings: Settings) -> AppSettings:
        return settings.app

    @provide
    def bot(self, settings: Settings) -> BotSettings:
        return settings.bot

    @provide
    def db(self, settings: Settings) -> DatabaseSettings:
        return settings.db

    @provide
    def redis_settings(self, settings: Settings) -> RedisSettings:
        return settings.redis

    @provide
    def llm(self, settings: Settings) -> LlmSettings:
        return settings.llm

    @provide
    def content(self, settings: Settings) -> ContentSettings:
        return settings.content


class InfraProvider(Provider):
    scope = Scope.APP

    @provide
    async def engine(self, settings: DatabaseSettings) -> AsyncIterator[AsyncEngine]:
        engine = build_engine(settings)
        yield engine
        await engine.dispose()

    @provide
    def session_factory(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return build_session_factory(engine)

    @provide
    async def redis(self, settings: RedisSettings) -> AsyncIterator[Redis]:
        client = build_redis(settings)
        yield client
        await client.aclose()

    @provide
    def scenarios(self, content: ContentSettings) -> ScenarioRegistry:
        """Валидация YAML на старте: битый сценарий роняет процесс, а не пользователя."""
        return load_registry(content.scenarios_dir)

    @provide
    async def llm_provider(self, settings: LlmSettings) -> AsyncIterator[LlmProvider]:
        provider = build_provider(settings)
        yield provider
        await provider.aclose()

    @provide
    def llm_cache(self, redis: Redis) -> LlmCache:
        return RedisLlmCache(redis)


class RepositoryProvider(Provider):
    scope = Scope.REQUEST

    @provide
    async def db_session(
        self, factory: async_sessionmaker[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        """Одна транзакция на апдейт. Коммит только при успешном выходе из обработчика."""
        async with factory() as session:
            yield session
            await session.commit()

    users = provide(SqlUserRepository, provides=UserRepository)
    sessions = provide(SqlSessionRepository, provides=SessionRepository)
    triage = provide(SqlTriageRepository, provides=TriageRepository)
    plans = provide(SqlPlanRepository, provides=PlanRepository)
    checkins = provide(SqlCheckinRepository, provides=CheckinRepository)
    llm_calls = provide(SqlLlmCallRepository, provides=LlmCallRepository)
    events = provide(SqlEventRepository, provides=EventRepository)
    export_source = provide(SqlExportRepository)


class ServiceProvider(Provider):
    scope = Scope.REQUEST

    @provide
    def llm_runner(
        self,
        provider: LlmProvider,
        settings: LlmSettings,
        audit: LlmCallRepository,
        cache: LlmCache,
    ) -> LlmRunner:
        return LlmRunner(provider=provider, settings=settings, audit=audit, cache=cache)

    user_service = provide(UserService)
    triage_service = provide(TriageService)
    tracker_service = provide(TrackerService)

    @provide
    def export_service(self, source: SqlExportRepository) -> ExportService:
        return ExportService(source)


def build_container() -> AsyncContainer:
    return make_async_container(
        SettingsProvider(),
        InfraProvider(),
        RepositoryProvider(),
        ServiceProvider(),
    )
