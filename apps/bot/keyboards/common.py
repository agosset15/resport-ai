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


class PainPointCB(CallbackData, prefix="pp"):
    action: str  # confirm | reject


class RouteCB(CallbackData, prefix="route"):
    choice: str  # doctor | self_rehab


class MoreScenariosCB(CallbackData, prefix="scenall"):
    pass


class SelfRehabCB(CallbackData, prefix="selfreh"):
    accept: bool


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


def scenarios_kb(
    choices: Sequence[ScenarioChoice], *, narrowed: bool = False
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for choice in choices:
        builder.button(text=choice.title, callback_data=ScenarioCB(scenario_id=choice.scenario_id))
    if narrowed:
        from apps.bot.texts import SHOW_ALL_SCENARIOS

        builder.button(text=SHOW_ALL_SCENARIOS, callback_data=MoreScenariosCB())
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


def pain_point_kb() -> InlineKeyboardMarkup:
    from apps.bot.texts import PAIN_POINT_CONFIRM_BUTTON, PAIN_POINT_REJECT_BUTTON

    builder = InlineKeyboardBuilder()
    builder.button(text=PAIN_POINT_CONFIRM_BUTTON, callback_data=PainPointCB(action="confirm"))
    builder.button(text=PAIN_POINT_REJECT_BUTTON, callback_data=PainPointCB(action="reject"))
    builder.adjust(1)
    return builder.as_markup()


def route_kb() -> InlineKeyboardMarkup:
    """Два пути после подтверждения точки боли: врач или самостоятельный план."""
    from apps.bot.texts import ROUTE_DOCTOR_BUTTON, ROUTE_SELF_BUTTON

    builder = InlineKeyboardBuilder()
    builder.button(text=ROUTE_DOCTOR_BUTTON, callback_data=RouteCB(choice="doctor"))
    builder.button(text=ROUTE_SELF_BUTTON, callback_data=RouteCB(choice="self_rehab"))
    builder.adjust(1)
    return builder.as_markup()


def self_rehab_kb() -> InlineKeyboardMarkup:
    """Явное согласие на самостоятельное восстановление: без него план не стартует."""
    from apps.bot.texts import SELF_REHAB_ACCEPT_BUTTON, SELF_REHAB_DECLINE_BUTTON

    builder = InlineKeyboardBuilder()
    builder.button(text=SELF_REHAB_ACCEPT_BUTTON, callback_data=SelfRehabCB(accept=True))
    builder.button(text=SELF_REHAB_DECLINE_BUTTON, callback_data=SelfRehabCB(accept=False))
    builder.adjust(1)
    return builder.as_markup()


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
