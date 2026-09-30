"""FastAPI: вебхук Telegram, healthz, задел под Mini App API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram.types import Update
from dishka.integrations.fastapi import setup_dishka
from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, status

from apps.bot.factory import build_runtime, set_commands
from apps.di import build_container
from core.config import get_settings
from core.domain.scenario import ScenarioRegistry
from infra.telemetry import get_logger, setup_logging

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    container = app.state.container
    # Реестр сценариев строится здесь: битый YAML роняет старт, а не пользователя.
    registry = await container.get(ScenarioRegistry)
    log.info("scenarios.loaded", ids=list(registry.ids()))

    bot, dispatcher = await build_runtime(container, settings.bot, settings.redis)

    app.state.bot = bot
    app.state.dispatcher = dispatcher

    if settings.bot.token.get_secret_value():
        await set_commands(bot)
        if not settings.bot.use_polling and settings.bot.webhook_base_url:
            await bot.set_webhook(
                settings.bot.webhook_url,
                secret_token=settings.bot.webhook_secret.get_secret_value(),
                drop_pending_updates=True,
            )
            log.info("webhook.set", url=settings.bot.webhook_url)

    try:
        yield
    finally:
        await bot.session.close()
        await container.close()


router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncEngine

    container = request.app.state.container
    engine = await container.get(AsyncEngine)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ready"}


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.app.log_level, settings.app.log_json)

    app = FastAPI(title="ReSport AI", version="0.1.0", lifespan=lifespan)
    # dishka вешает middleware — только до старта приложения, не в lifespan.
    container = build_container()
    app.state.container = container
    setup_dishka(container=container, app=app)
    app.include_router(router)

    @app.post(settings.bot.webhook_path)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        expected = settings.bot.webhook_secret.get_secret_value()
        if x_telegram_bot_api_secret_token != expected:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="bad secret")
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": request.app.state.bot})
        await request.app.state.dispatcher.feed_update(request.app.state.bot, update)
        return {"ok": True}

    return app


app = create_app()
