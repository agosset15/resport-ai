"""Клавиатуры и callback-данные. Бот — транспорт: вся логика осталась в core."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from apps.bot.texts import FEELING_LABELS, SPORT_LABELS
from core.domain.enums import Feeling, Sport
from core.domain.scenario import Option, PlanTask
from core.services.dto import ScenarioChoice


class ConsentCB(CallbackData, prefix="consent"):
    accept: bool


class SportCB(CallbackData, prefix="sport"):
    sport: str


class ScenarioCB(CallbackData, prefix="scen"):
    scenario_id: str


class AnswerCB(CallbackData, prefix="ans"):
    question_key: str
    option_id: str


class TaskCB(CallbackData, prefix="task"):
    key: str


class CheckinCB(CallbackData, prefix="chk"):
    action: str  # tasks_done | feeling | start
    value: str = ""


class ReminderCB(CallbackData, prefix="rem"):
    value: str  # HH:MM | skip


class MenuCB(CallbackData, prefix="menu"):
    action: str  # plan | restart | specialist


def consent_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Принимаю", callback_data=ConsentCB(accept=True))
    builder.adjust(1)
    return builder.as_markup()


def sports_kb(sports: Sequence[Sport]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sport in sports:
        builder.button(text=SPORT_LABELS[sport], callback_data=SportCB(sport=sport.value))
    builder.adjust(1)
    return builder.as_markup()


def scenarios_kb(choices: Sequence[ScenarioChoice]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for choice in choices:
        builder.button(text=choice.title, callback_data=ScenarioCB(scenario_id=choice.scenario_id))
    builder.adjust(1)
    return builder.as_markup()


def options_kb(question_key: str, options: Sequence[Option]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for option in options:
        builder.button(
            text=option.label,
            callback_data=AnswerCB(question_key=question_key, option_id=option.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def specialist_kb(url: str) -> InlineKeyboardMarkup:
    from apps.bot.texts import SPECIALIST_BUTTON

    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=SPECIALIST_BUTTON, url=url)]]
    )


def tasks_kb(tasks: Sequence[PlanTask], selected: Sequence[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for task in tasks:
        mark = "☑️" if task.key in selected else "⬜"
        builder.button(text=f"{mark} {task.text}", callback_data=TaskCB(key=task.key))
    builder.button(text="Дальше →", callback_data=CheckinCB(action="tasks_done"))
    builder.adjust(1)
    return builder.as_markup()


def feeling_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for feeling, label in FEELING_LABELS.items():
        builder.button(text=label, callback_data=CheckinCB(action="feeling", value=feeling.value))
    builder.adjust(1)
    return builder.as_markup()


def checkin_start_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Сделать чек-ин", callback_data=CheckinCB(action="start"))
    return builder.as_markup()


REMINDER_PRESETS = ("09:00", "13:00", "19:00", "21:00")


def reminder_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for preset in REMINDER_PRESETS:
        builder.button(text=preset, callback_data=ReminderCB(value=preset))
    builder.button(text="Без напоминаний", callback_data=ReminderCB(value="skip"))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def feeling_from(value: str) -> Feeling:
    return Feeling(value)
