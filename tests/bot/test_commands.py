"""Меню команд Telegram должно совпадать со справкой и с зарегистрированными хендлерами.

Эта проверка появилась не на пустом месте: после трёх фаз в меню остались только пять
старых команд. Хендлеры работали, /help их перечислял, но в меню Telegram их не было —
то есть пользователь их просто не видел.
"""

from __future__ import annotations

import importlib
import pkgutil
import re

from aiogram import Router
from aiogram.filters import Command

import apps.bot.handlers
from apps.bot import texts
from apps.bot.factory import COMMANDS

#: Команды, которые намеренно не показываются в меню: только для администраторов.
ADMIN_ONLY = {"stats", "export_sessions", "export_checkins"}


def menu_commands() -> set[str]:
    return {name for name, _ in COMMANDS}


def help_commands() -> set[str]:
    # В тексте справки есть HTML-теги, поэтому берём только то, что похоже на команду.
    found = set(re.findall(r"/([a-z][a-z_]{2,})", texts.HELP))
    return found


def all_routers() -> list[Router]:
    """Роутеры из всех модулей apps/bot/handlers — новый модуль попадёт сюда сам."""
    routers: list[Router] = []
    for info in pkgutil.iter_modules(apps.bot.handlers.__path__):
        module = importlib.import_module(f"apps.bot.handlers.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, Router):
            routers.append(router)
    return routers


def registered_commands() -> set[str]:
    """Команды из фильтров всех хендлеров."""
    names: set[str] = set()
    for router in all_routers():
        for observer in router.observers.values():
            for handler in observer.handlers:
                for flt in handler.filters or []:
                    callback = getattr(flt, "callback", None)
                    if isinstance(callback, Command):
                        names.update(
                            str(command)
                            for command in callback.commands
                            if isinstance(command, str)
                        )
    return names


class TestCommandMenu:
    def test_menu_has_no_duplicates(self) -> None:
        assert len(menu_commands()) == len(COMMANDS)

    def test_menu_matches_help(self) -> None:
        assert menu_commands() == help_commands()

    def test_descriptions_are_short_enough(self) -> None:
        """Telegram обрезает описание команды на 256 символах."""
        for name, description in COMMANDS:
            assert description, name
            assert len(description) <= 256, name

    def test_names_are_valid_for_telegram(self) -> None:
        for name, _ in COMMANDS:
            assert re.fullmatch(r"[a-z0-9_]{1,32}", name), name


class TestHandlersAreRegistered:
    def test_every_menu_command_has_a_handler(self) -> None:
        """Иначе в меню висит кнопка, на которую бот не отвечает."""
        registered = registered_commands()
        missing = menu_commands() - registered
        assert not missing, f"в меню есть, а хендлера нет: {sorted(missing)}"

    def test_every_handler_is_in_the_menu_or_admin_only(self) -> None:
        registered = registered_commands()
        hidden = registered - menu_commands() - ADMIN_ONLY
        assert not hidden, f"хендлер есть, а в меню команды нет: {sorted(hidden)}"
