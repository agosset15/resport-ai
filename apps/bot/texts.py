"""Все тексты бота в одном месте.

ЧЕРНОВИК: финальные формулировки (особенно дисклеймер и текст согласия) даёт заказчик —
пункты 2 и 4 списка «что нужно до старта». Менять тут, а не в хендлерах.
"""

from __future__ import annotations

from core.domain.enums import (
    DailyCapacity,
    Feeling,
    ItemStatus,
    PlanSource,
    Sport,
    Swelling,
)
from core.domain.supplement import Supplement
from core.services.dto import DailyPlanView
from core.services.progress import DayMark, ProgressView
from core.supplements.matcher import StopReason

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
CLASSIFY_NARROWED = "Похоже на одно из этого. Что ближе?"
SHOW_ALL_SCENARIOS = "Показать все варианты"
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

SUPPLEMENT_STOP_LABELS: dict[StopReason, str] = {
    StopReason.PROFILE_INCOMPLETE: "часть анкеты не заполнена",
    StopReason.AGE_UNKNOWN: "не указан возраст",
    StopReason.MINOR: "подбор добавок доступен только совершеннолетним",
    StopReason.PREGNANCY: "беременность",
    StopReason.BREASTFEEDING: "грудное вскармливание",
    StopReason.UPCOMING_SURGERY: "предстоящая операция",
    StopReason.MEDICATIONS: "принимаются лекарства — возможно взаимодействие",
}

SUPPLEMENT_INTRO = (
    "<b>Добавки на период восстановления</b>\n\n"
    "Сначала несколько вопросов — без них подбирать нельзя. Приём добавок "
    "добровольный: это не лечение и не часть обязательной программы.\n\n"
    "<i>Добавки не проходят проверку на безопасность и эффективность до продажи — "
    "за это отвечает производитель, а не регулятор. Они могут взаимодействовать с "
    "лекарствами, искажать результаты анализов и быть опасными во время операции. "
    "Источник предупреждений: FDA, «FDA 101: Dietary Supplements».</i>"
)
SUPPLEMENT_QUESTION = "<b>Вопрос {number} из {total}</b>\n\n{text}"
SUPPLEMENT_QUESTION_HINT = "\n\n<i>{hint}</i>"
SUPPLEMENT_NEED_NUMBER = "Нужно число — сколько тебе полных лет."
SUPPLEMENT_NEED_BUTTON = "Ответь кнопкой, пожалуйста."
SUPPLEMENT_PROFILE_SAVED = "Записал ответы."
SUPPLEMENT_NO_PROFILE = "Сначала пройди анкету: /supplements."

SUPPLEMENT_SUSPENDED = (
    "<b>Подбор приостановлен</b>\n\n"
    "Причины:\n{reasons}\n\n"
    "В таких случаях я не подбираю добавки сам — это нужно обсудить со специалистом. "
    "Подтверждение, что ты прочитал предупреждение, этого не меняет."
)
SUPPLEMENT_NOTHING_SUITABLE = (
    "Подходящего варианта нет — прямо говорю об этом, а не предлагаю хоть что-нибудь.\n\n"
    "База добавок заполняется заказчиком и проверяется врачом; пока в ней нет "
    "подтверждённых записей, подбор ничего не предложит."
)
SUPPLEMENT_LIST = "Вот что подходит по твоим ответам. Открой карточку, чтобы прочитать детали:"
SUPPLEMENT_ACTIVE_LIST = "Добавки, которые ты принимаешь:"
SUPPLEMENT_NONE_ACTIVE = "Сейчас ты не принимаешь добавок. Подобрать — /supplements."
SUPPLEMENT_GONE = "Эта запись больше недоступна."

SUPPLEMENT_ADD_BUTTON = "Добавить в план"
SUPPLEMENT_SKIP_BUTTON = "Не принимать"
SUPPLEMENT_REACTION_BUTTON = "Сообщить о реакции"
SUPPLEMENT_ADDED = (
    "Добавил «{product}» в план. Отмечать приём можно в /today.\n\n"
    "Приём добавок не влияет на процент прохождения программы: он считается отдельно."
)
SUPPLEMENT_DECLINED = (
    "Записал отказ. Это не снижает процент прохождения программы — добавки в него не входят."
)
SUPPLEMENT_ASK_REACTION = "Опиши, что произошло: что почувствовал, когда, после какой дозы."
SUPPLEMENT_REACTION_MILD = (
    "<b>Записал и остановил приём.</b>\n\n"
    "Прекрати принимать эту добавку и обратись за медицинской помощью или советом — "
    "так советует FDA при любой нежелательной реакции.\n\n"
    "Запись попадёт в отчёт, её можно показать врачу."
)
SUPPLEMENT_REACTION_SEVERE = (
    "<b>Похоже на тяжёлую реакцию. Вызывай экстренную помощь.</b>\n\n"
    "Приём я остановил и записал всё в дневник. Не жди, пока станет лучше, "
    "и не принимай добавку снова.\n\n"
    "Если трудно дышать, отекает лицо или горло, появилась сыпь по всему телу, "
    "резкая слабость или спутанность — это повод для экстренной помощи."
)


def supplement_card(supplement: Supplement) -> str:
    """Карточка БАДа: всё, что требует ТЗ, включая источник и дату обновления."""
    lines = [
        f"<b>{supplement.product}</b>",
        f"Производитель: {supplement.manufacturer}",
        "",
        "<b>Состав</b>",
    ]
    lines += [f"• {component.human()}" for component in supplement.composition]
    if supplement.excipients:
        lines.append("Вспомогательные компоненты: " + ", ".join(supplement.excipients))
    if supplement.allergens:
        lines.append("<b>Аллергены:</b> " + ", ".join(supplement.allergens))

    lines += ["", "<b>Зачем предлагается</b>", supplement.rationale]
    lines += ["", "<b>Чего ожидать не стоит</b>", supplement.benefit_limits]
    lines += [
        "",
        "<b>Как принимать</b>",
        supplement.intake.dose_text,
        f"Длительность: {supplement.intake.duration_text}",
    ]

    if supplement.contraindications:
        lines += ["", "<b>Противопоказания</b>"]
        lines += [f"• {item}" for item in supplement.contraindications]
    if supplement.side_effects:
        lines += ["", "<b>Возможные побочные эффекты</b>"]
        lines += [f"• {item}" for item in supplement.side_effects]
    if supplement.interactions:
        lines += ["", "<b>Взаимодействия</b>"]
        lines += [f"• {i.with_what}: {i.note}" for i in supplement.interactions]
    if supplement.adverse_reaction_actions:
        lines += ["", "<b>Если стало плохо</b>", supplement.adverse_reaction_actions]

    lines += [
        "",
        f"<i>Источник: {supplement.source.title} ({supplement.source.url})</i>",
        f"<i>Сведения получены: {supplement.source.retrieved_at}, "
        f"запись обновлена: {supplement.updated_at}</i>",
    ]
    if supplement.needs_review:
        lines.append("<i>⚠️ Запись не подтверждена врачом — показана только для проверки.</i>")
    return "\n".join(lines)


PRESCRIPTION_ASK = (
    "<b>План по назначению специалиста</b>\n\n"
    "Пришли назначение текстом — как написал врач или реабилитолог. "
    "Можно одним сообщением, по одному пункту на строку.\n\n"
    "Я перенесу пункты дословно и <b>не буду менять назначенную нагрузку</b>. "
    "Если нужно её изменить — это согласуют со специалистом, а не со мной."
)
PRESCRIPTION_TOO_SHORT = "Пришли назначение подробнее — пары слов мало."
PRESCRIPTION_NEEDS_SESSION = (
    "Сначала пройдём короткий опрос по травме: нажми /start. "
    "После него я смогу собрать план по назначению."
)
PRESCRIPTION_NOT_PARSED = (
    "Не смог разобрать назначение на пункты. Попробуй прислать по одному пункту на строку."
)
PRESCRIPTION_PREVIEW_HEADER = "<b>Вот что я перенёс из назначения</b>\n"
PRESCRIPTION_PREVIEW_LIMITS = "\n<b>Ограничения:</b>"
PRESCRIPTION_PREVIEW_DAYS = "\nСрок: {days} дней"
PRESCRIPTION_PREVIEW_FALLBACK = (
    "\n<i>Разобрал по строкам, без изменений — это твой текст как есть.</i>"
)
PRESCRIPTION_PREVIEW_FOOTER = "\nВсё верно? Дозировки и формулировки я оставил как в назначении."
PRESCRIPTION_ACCEPT_BUTTON = "Всё верно, собрать план"
PRESCRIPTION_RETRY_BUTTON = "Прислать заново"
PRESCRIPTION_RETRY = "Хорошо, пришли назначение заново."
PRESCRIPTION_PLAN_STARTED = (
    "План по назначению собран, {days} дней. Нагрузку я не меняю — "
    "изменения согласуй со специалистом."
)

PAIN_POINT_ASK = "Посмотри на картинку: похоже на твой случай? Отметь, где болит.\n\n{title}"
PAIN_POINT_CONFIRM_BUTTON = "Да, болит здесь"
PAIN_POINT_REJECT_BUTTON = "Болит не здесь"
PAIN_POINT_REJECTED = "Понял. Тогда выбери, что ближе к твоей ситуации:"

CHOOSE_ROUTE = (
    "<b>Что дальше?</b>\n\n"
    "Можно записаться к специалисту — он осмотрит травму и поставит диагноз.\n"
    "Или можно восстанавливаться самостоятельно: я задам несколько вопросов "
    "по безопасности и, если тревожных признаков не будет, дам план."
)
ROUTE_DOCTOR_BUTTON = "Запись к врачу"
ROUTE_SELF_BUTTON = "Самостоятельная реабилитация"
SELF_REHAB_SURVEY_FIRST = (
    "Хорошо. Сначала — несколько вопросов по безопасности: мне нужно убедиться, "
    "что самостоятельное восстановление тебе не навредит."
)

SELF_REHAB_HEADER = "<b>Что делать дальше</b>\n\n"
SELF_REHAB_DISCLAIMER = (
    "\n\n<b>Прежде чем начнём — важное</b>\n"
    "Тревожных признаков в твоих ответах нет, поэтому предлагаю восстанавливаться "
    "самостоятельно по проверенному сценарию.\n\n"
    "Я не ставлю диагноз и <b>не даю никаких гарантий</b>: я не видел травму, не осматривал "
    "тебя и не делал снимков. Это не допуск к тренировкам и не замена очному осмотру.\n\n"
    "Останови план и покажись врачу, если боль или отёк растут, появились онемение, "
    "холодная или синюшная кожа, деформация, температура — или если за несколько дней "
    "не становится лучше.\n\n"
    "Решение продолжать ты принимаешь сам."
)
SELF_REHAB_ACCEPT_BUTTON = "Понимаю, начинаем"
SELF_REHAB_DECLINE_BUTTON = "Лучше к специалисту"
SELF_REHAB_DECLINED = (
    "Понял. Самостоятельный план не запускаю.\n\n"
    "Покажись специалисту: он осмотрит травму и скажет, что можно делать."
)
SELF_REHAB_CONSENT_REQUIRED = "Сначала подтверди, что прочитал предупреждение."

PLAN_INTRO_HEADER = "<b>Что делать дальше</b>\n\n"
PLAN_STARTED = "Плана хватит на {days} дней. Начнём с первого этапа."

ASK_REMINDER_TIME = (
    "Во сколько напоминать про чек-ин? Можно выбрать кнопкой или написать время, например 19:30."
)
REMINDER_SET = "Буду напоминать в {time}. Можно изменить командой /reminder."
REMINDER_BAD_FORMAT = "Не понял время. Напиши в формате ЧЧ:ММ, например 19:30."
REMINDER_PING = "Время чек-ина. Как прошёл день?"
REMINDER_TODAY = "Напоминаю про восстановление.\n\n{plan}"

REPORT_PREVIEW_HEADER = "<b>Отчёт за период {start} — {end}</b>"
REPORT_PREVIEW_BODY = (
    "\n\nПройдено занятий: {done}{total_part}\n"
    "Частично: {partial} · пропущено: {skipped} · нет данных: {no_data}\n"
    "Записей о самочувствии: {wellbeing}\n"
    "Вопросов к приёму: {questions}"
)
REPORT_PREVIEW_TOTAL = " из {total} ({percent}% программы)"
REPORT_PREVIEW_FOOTER = "\n\nМожно скачать файлом и показать врачу. Это не диагноз и не заключение."
REPORT_PDF_BUTTON = "Скачать PDF"
REPORT_TEXT_BUTTON = "Скачать текстом"
REPORT_NO_DATA = "Пока нечего показывать: отметь план командой /today и запиши самочувствие /diary."
REPORT_PDF_UNAVAILABLE = (
    "PDF собрать не удалось — на сервере нет шрифта с кириллицей. "
    "Отправляю отчёт текстом, содержание то же."
)

DAY_MARK_ICONS: dict[DayMark, str] = {
    DayMark.DONE: "🟩",
    DayMark.PARTIAL: "🟨",
    DayMark.SKIPPED: "⬜",
    DayMark.NO_DATA: "▫️",
}

PROGRESS_HEADER = "<b>Мой прогресс</b>\n{plan_title}"
PROGRESS_SESSIONS = "\n\nПройдено {done} из {total} занятий — {percent}% программы"
PROGRESS_SESSIONS_NO_TOTAL = (
    "\n\nПройдено занятий: {done}. Полный объём программы пока не задан, "
    "поэтому общий процент не показываю."
)
PROGRESS_PARTIAL = "\nЧастично выполнено: {partial} — в зачёт программы не идёт"
PROGRESS_STAGE = "\n\nЭтап {stage_number} из {stage_total}: {stage_title} (день {day} из {days})"
PROGRESS_CALENDAR = "\n\n<b>Регулярность</b>\n{calendar}"
PROGRESS_CALENDAR_LEGEND = "\n🟩 выполнено · 🟨 частично · ⬜ пропуск · ▫️ нет данных"
PROGRESS_TREND_HEADER = "\n\n<b>Самочувствие</b>"
PROGRESS_TREND_START = "\nБоль была {first} из 10, сейчас {last} из 10 — {verdict}"
PROGRESS_TREND_PREV = "\nС прошлой записи: {verdict}"
PROGRESS_TREND_NONE = "\nЗаписей о самочувствии пока нет — отметь его командой /diary."
PROGRESS_NEXT = "\n\n<b>Ближайшая цель</b>\n{checkpoint}"
PROGRESS_DISCLAIMER = (
    "\n\n<i>Процент прохождения программы — это про выполненные занятия, "
    "а не про то, насколько зажила травма. Это разные вещи.</i>"
)
PROGRESS_COMPLETED = "\n\n<b>Программа пройдена.</b>"
PROGRESS_REVISED = (
    "\n\n<i>План менялся {count} раз(а), поэтому прогресс пересчитан по текущей версии.</i>"
)


def _pain_verdict(delta: int | None) -> str:
    if delta is None:
        return "сравнить пока не с чем"
    if delta < 0:
        return f"меньше на {abs(delta)}"
    if delta > 0:
        return f"больше на {delta}"
    return "без изменений"


def progress_text(view: ProgressView, revisions: int = 0) -> str:
    text = PROGRESS_HEADER.format(plan_title=view.plan_title)

    percent = view.percent
    if percent is None:
        text += PROGRESS_SESSIONS_NO_TOTAL.format(done=view.completed_sessions)
    else:
        text += PROGRESS_SESSIONS.format(
            done=view.completed_sessions, total=view.total_sessions, percent=percent
        )
    if view.partial_sessions:
        text += PROGRESS_PARTIAL.format(partial=view.partial_sessions)

    if view.program_completed:
        text += PROGRESS_COMPLETED
    else:
        text += PROGRESS_STAGE.format(
            stage_number=view.stage_index + 1,
            stage_total=view.stage_total,
            stage_title=view.stage_title,
            day=view.stage_day,
            days=view.stage_days,
        )

    if view.calendar:
        calendar = "".join(DAY_MARK_ICONS[cell.mark] for cell in view.calendar)
        text += PROGRESS_CALENDAR.format(calendar=calendar) + PROGRESS_CALENDAR_LEGEND

    text += PROGRESS_TREND_HEADER
    trend = view.trend
    if trend.last_pain is None:
        text += PROGRESS_TREND_NONE
    else:
        text += PROGRESS_TREND_START.format(
            first=trend.first_pain,
            last=trend.last_pain,
            verdict=_pain_verdict(trend.since_start),
        )
        if trend.since_previous is not None:
            text += PROGRESS_TREND_PREV.format(verdict=_pain_verdict(trend.since_previous))

    text += PROGRESS_NEXT.format(checkpoint=view.next_checkpoint)
    if revisions:
        text += PROGRESS_REVISED.format(count=revisions)
    return text + PROGRESS_DISCLAIMER


SWELLING_LABELS: dict[Swelling, str] = {
    Swelling.NONE: "Отёка нет",
    Swelling.MILD: "Небольшой",
    Swelling.MODERATE: "Умеренный",
    Swelling.SEVERE: "Сильный",
}

CAPACITY_LABELS: dict[DailyCapacity, str] = {
    DailyCapacity.FULL: "Всё как обычно",
    DailyCapacity.LIMITED: "Кое-что даётся труднее",
    DailyCapacity.MINIMAL: "Многое не получается",
}

WELLBEING_ASK_PAIN = (
    "<b>Самочувствие за сегодня</b>\n\n"
    "Насколько болит сейчас? 0 — не болит совсем, 10 — сильнее некуда."
)
WELLBEING_ASK_SWELLING = "Что с отёком?"
WELLBEING_ASK_CAPACITY = "Что получается в быту — ходить, подниматься по лестнице, одеваться?"
WELLBEING_ASK_NOTE = "Хочешь что-то добавить своими словами? Напиши — или отправь «-», если нечего."
WELLBEING_SAVED = "Записал. Это попадёт в дневник и в отчёт."
WELLBEING_ALREADY_DONE = "За сегодня запись уже есть — новая её заменит."
WELLBEING_INCOMPLETE = "Часть ответов потерялась, давай заново."

ITEM_STATUS_LABELS: dict[ItemStatus, str] = {
    ItemStatus.DONE: "Выполнено",
    ItemStatus.PARTIAL: "Частично",
    ItemStatus.SKIPPED: "Пропущено",
}

ITEM_STATUS_ICONS: dict[ItemStatus | None, str] = {
    ItemStatus.DONE: "✅",
    ItemStatus.PARTIAL: "🟡",
    ItemStatus.SKIPPED: "⬜",
    None: "▫️",
}

DAILY_HEADER = (
    "<b>План на сегодня</b>\n"
    "{plan_title}\n"
    "Этап {stage_number} из {stage_total}: {stage_title}\n"
    "День {day_number} из {day_total}"
)
DAILY_PRESCRIPTION_NOTE = (
    "\n\n<i>План собран из назначения специалиста. Нагрузку я не меняю — "
    "изменения согласуй с ним.</i>"
)
DAILY_PROGRESS_LINE = "\n\nОтмечено: {done} выполнено, {partial} частично, {skipped} пропущено"
DAILY_ALL_MARKED = "\n\nВсё на сегодня отмечено. Осталось записать самочувствие."
DAILY_EMPTY = "На этом этапе упражнений нет — только наблюдение."
DAILY_WELLBEING_BUTTON = "Записать самочувствие"
DAILY_WELLBEING_DONE_BUTTON = "Самочувствие записано ✓"

ITEM_CARD_TITLE = "<b>{title}</b>"
ITEM_CARD_DOSAGE = "\n<b>Сколько:</b> {dosage}"
ITEM_CARD_SUPPLEMENT_NOTE = (
    "\n<i>Это приём добавки. Он не влияет на процент прохождения программы.</i>"
)
ITEM_CARD_LIMITS = "\n<b>Ограничения:</b>\n{limits}"
ITEM_CARD_LOOKUP = "\n<i>{hint}</i>"
ITEM_CARD_STATUS = "\n\nОтметка: {status}"
ITEM_CARD_COMMENT = "\nКомментарий: {comment}"
ITEM_DONE_BUTTON = "✅ Выполнено"
ITEM_PARTIAL_BUTTON = "🟡 Частично"
ITEM_SKIP_BUTTON = "⬜ Пропустил"
ITEM_COMMENT_BUTTON = "💬 Комментарий"
ITEM_REFRESH_BUTTON = "← К плану на сегодня"
ITEM_ASK_COMMENT = "Напиши комментарий к этому пункту — что мешало или как ощущалось."
ITEM_COMMENT_SAVED = "Записал комментарий."
ITEM_MARKED = "Отметил: {status}"
ITEM_GONE = "Этот пункт больше не в плане на сегодня."


def daily_text(view: DailyPlanView) -> str:
    text = DAILY_HEADER.format(
        plan_title=view.plan_title,
        stage_number=view.stage_index + 1,
        stage_total=view.stage_total,
        stage_title=view.stage_title,
        day_number=view.day_number,
        day_total=view.day_total,
    )
    if view.source is PlanSource.PRESCRIPTION:
        text += DAILY_PRESCRIPTION_NOTE
    if view.stage_description:
        text += f"\n\n<i>{view.stage_description}</i>"
    if not view.items:
        return text + "\n\n" + DAILY_EMPTY

    text += "\n"
    for index, item in enumerate(view.items, start=1):
        icon = ITEM_STATUS_ICONS[item.status] if item.status else ITEM_STATUS_ICONS[None]
        text += f"\n{icon} {index}. {item.title}"
        if item.dosage:
            text += f" — {item.dosage}"
    text += DAILY_PROGRESS_LINE.format(done=view.done, partial=view.partial, skipped=view.skipped)
    if view.all_marked and not view.wellbeing_done:
        text += DAILY_ALL_MARKED
    return text


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
    "/today — план на сегодня\n"
    "/diary — записать самочувствие\n"
    "/progress — мой прогресс\n"
    "/report — отчёт за период\n"
    "/prescription — план по назначению врача\n"
    "/supplements — подбор добавок\n"
    "/my_supplements — что принимаю\n"
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
