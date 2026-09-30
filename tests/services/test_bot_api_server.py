"""Базовый URL Bot API: официальный по умолчанию, свой — из настроек."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from apps.bot.factory import build_bot
from core.config import BotSettings


def _settings(**kwargs: object) -> BotSettings:
    # _env_file=None: тест не зависит от локального .env
    return BotSettings(_env_file=None, token=SecretStr("1:test"), **kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_default_api_server_is_official() -> None:
    bot = build_bot(_settings())
    try:
        assert bot.session.api.api_url(token="1:test", method="getMe") == (
            "https://api.telegram.org/bot1:test/getMe"
        )
        assert bot.session.api.is_local is False
    finally:
        await bot.session.close()


@pytest.mark.asyncio
async def test_custom_api_server_url() -> None:
    bot = build_bot(_settings(api_server_url="http://localhost:8081/", api_server_local=True))
    try:
        assert bot.session.api.api_url(token="1:test", method="getMe") == (
            "http://localhost:8081/bot1:test/getMe"
        )
        assert bot.session.api.file_url(token="1:test", path="a/b.jpg") == (
            "http://localhost:8081/file/bot1:test/a/b.jpg"
        )
        assert bot.session.api.is_local is True
    finally:
        await bot.session.close()
