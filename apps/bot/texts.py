"""Все тексты бота в одном месте.

ЧЕРНОВИК: финальные формулировки (особенно дисклеймер и текст согласия) даёт заказчик —
пункты 2 и 4 списка «что нужно до старта». Менять тут, а не в хендлерах.
"""

from __future__ import annotations

from core.domain.enums import Feeling, Sport

SPORT_LABELS: dict[Sport, str] = {
    Sport.FOOTBALL: "⚽ Футбол",
    Sport.BASKETBALL: "🏀 Баскетбол",
}

FEELING_LABELS: dict[Feeling, str] = {
    Feeling.BETTER: "🙂 Лучше",
    Feeling.SAME: "😐 Без изменений",
    Feeling.WORSE: "🙁 Хуже",
}

START = (
    "Привет! Я помогу разобраться, что делать с травмой или болью после тренировки.\n\n"
    "Задам несколько вопросов и предложу понятный следующий шаг: либо план восстановления, "
    "либо совет обратиться к специалисту."
)

DISCLAIMER = (
    "<b>Важно, прежде чем начнём</b>\n\n"
    "Я не врач и не ставлю диагнозы. Я не оказываю медицинскую помощь и не заменяю "
    "очный осмотр специалиста.\n\n"
    "Я задаю вопросы по заранее составленным сценариям и показываю, что обычно делают "
    "в похожей ситуации. Решение о лечении принимаешь ты вместе с врачом.\n\n"
    "Если тебе прямо сейчас очень больно, нога или рука не работает, есть деформация, "
    "онемение или сильный отёк — не пиши боту, обратись за очной помощью.\n\n"
    "Я сохраняю твои ответы и отметки в трекере, чтобы показывать прогресс.\n\n"
    "Нажимая «Принимаю», ты подтверждаешь, что прочитал это и согласен."
)

CONSENT_ACCEPTED = "Принято. Теперь выбери вид спорта."
CONSENT_REQUIRED = "Чтобы продолжить, нужно принять условия."

CHOOSE_SPORT = "Каким видом спорта занимаешься?"
DESCRIBE_PROBLEM = (
    "Опиши своими словами, что случилось и что беспокоит.\n\n"
    "Например: «вчера на игре подвернул голеностоп, сейчас опухло и больно наступать»."
)
COMPLAINT_TOO_SHORT = "Напиши чуть подробнее — пары слов мало, чтобы понять ситуацию."

CLASSIFY_FALLBACK = "Не могу уверенно определить ситуацию по описанию. Выбери, что ближе:"
CLASSIFY_OK = "Понял. Похоже на: <b>{title}</b>\n\nЗадам несколько уточняющих вопросов."

QUESTION = "<b>Вопрос {number} из {total}</b>\n\n{text}"
QUESTION_HINT = "\n\n<i>{hint}</i>"
ANSWER_NOT_UNDERSTOOD = "Не понял ответ. Выбери, пожалуйста, вариант кнопкой:"
FREE_TEXT_ALLOWED = "\n\nМожно ответить кнопкой или написать своими словами."

REFER_SPECIALIST_HEADER = "<b>Что делать дальше</b>\n\n"
REFER_SPECIALIST_FOOTER = (
    "\n\nЭто не диагноз. Очный осмотр нужен, чтобы понять, что именно произошло."
)
SPECIALIST_BUTTON = "Обратиться к специалисту"

PLAN_INTRO_HEADER = "<b>Что делать дальше</b>\n\n"
PLAN_STARTED = "Плана хватит на {days} дней. Начнём с первого этапа."

ASK_REMINDER_TIME = (
    "Во сколько напоминать про чек-ин? Можно выбрать кнопкой или написать время, например 19:30."
)
REMINDER_SET = "Буду напоминать в {time}. Можно изменить командой /reminder."
REMINDER_BAD_FORMAT = "Не понял время. Напиши в формате ЧЧ:ММ, например 19:30."
REMINDER_PING = "Время чек-ина. Как прошёл день?"

STAGE_HEADER = (
    "<b>{plan_title}</b>\n"
    "Этап {stage_number} из {stage_total}: {stage_title}\n"
    "День {day_number} из {day_total}"
)
STAGE_TASKS_HEADER = "\n\n<b>Задачи на сегодня:</b>"
STAGE_DONE_TODAY = "\n\nЧек-ин за сегодня уже сделан. Возвращайся завтра."
CHECKIN_PROMPT_TASKS = "Отметь, что сделал сегодня, и нажми «Дальше»."
CHECKIN_PROMPT_FEELING = "Как самочувствие по сравнению со вчера?"
CHECKIN_SAVED = "Записал."
STAGE_ADVANCED = "🎉 {text}"
PLAN_COMPLETED = "<b>План пройден</b>\n\n{text}"
PLAN_ESCALATED = "<b>Остановим план</b>\n\n{text}"

NO_ACTIVE_PLAN = "Активного плана нет. Нажми /start, чтобы пройти опрос."
NO_ACTIVE_SESSION = "Активного опроса нет. Нажми /start, чтобы начать."
SESSION_RESTARTED = "Начинаем заново."

HELP = (
    "<b>Команды</b>\n"
    "/start — начать заново\n"
    "/plan — текущий этап плана\n"
    "/checkin — отметить день\n"
    "/reminder — изменить время напоминания\n"
    "/help — эта справка\n\n"
    "Бот не ставит диагнозы и не заменяет врача."
)

ERROR = "Что-то пошло не так. Попробуй ещё раз или напиши {support}."
ADMIN_ONLY = "Команда доступна только администраторам."
EXPORT_EMPTY = "Пока нечего выгружать."


def stage_text(
    plan_title: str,
    stage_number: int,
    stage_total: int,
    stage_title: str,
    day_number: int,
    day_total: int,
    description: str | None,
    tasks: list[str],
    done: bool,
) -> str:
    text = STAGE_HEADER.format(
        plan_title=plan_title,
        stage_number=stage_number,
        stage_total=stage_total,
        stage_title=stage_title,
        day_number=day_number,
        day_total=day_total,
    )
    if description:
        text += f"\n\n<i>{description}</i>"
    if tasks:
        text += STAGE_TASKS_HEADER
        text += "\n" + "\n".join(f"• {task}" for task in tasks)
    if done:
        text += STAGE_DONE_TODAY
    return text
