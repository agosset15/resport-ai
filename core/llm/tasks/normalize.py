"""Задача 2: превратить свободный ответ пользователя в один из вариантов вопроса.

Не распозналось — переспрашиваем кнопками. Угадывать нельзя: ответ идёт в маршрутизацию.
"""

from __future__ import annotations

from uuid import UUID

from core.domain.enums import LlmTask
from core.domain.scenario import Question
from core.llm.runner import LlmRunner
from core.llm.schemas import UNCLEAR, build_normalize_model
from core.scenarios.matching import tokens

UNKNOWN_OPTION = "unknown"

#: Явные формулировки «не знаю»: отвечать переспросом на них бессмысленно,
#: у большинства вопросов для этого есть собственный вариант.
DONT_KNOW = frozenset(
    {
        "не знаю",
        "незнаю",
        "хз",
        "не уверен",
        "не уверена",
        "не понимаю",
        "не могу определить",
        "сложно сказать",
    }
)

SYSTEM = """Ты сопоставляешь свободный ответ спортсмена с вариантами ответа на вопрос.

Правила:
- Выбирай ровно один id из списка вариантов.
- Если ответ не соответствует ни одному варианту, двусмысленный или содержит новую жалобу —
  верни "unclear". Лучше переспросить, чем угадать.
- Не интерпретируй и не додумывай: сопоставляй то, что написано.
- Отвечай строго в заданной JSON-схеме."""


def _user_prompt(question: Question, raw_text: str) -> str:
    options = "\n".join(f"- {o.id}: {o.label}" for o in question.options)
    hint = f"Пояснение к вопросу: {question.hint}\n\n" if question.hint else ""
    return (
        f"Вопрос: {question.text}\n\n"
        f"{hint}"
        f"Варианты ответа:\n{options}\n\n"
        f"Ответ спортсмена:\n{raw_text.strip()}"
    )


async def normalize_answer(
    runner: LlmRunner,
    question: Question,
    raw_text: str,
    *,
    session_id: UUID | None = None,
) -> str | None:
    """Возвращает option_id или None (фоллбэк: переспрос кнопками)."""
    if not raw_text.strip():
        return None

    direct = _direct_match(question, raw_text)
    if direct is not None:
        return direct

    model_cls = build_normalize_model(question.option_ids())
    result = await runner.run(
        LlmTask.NORMALIZE_ANSWER,
        system=SYSTEM,
        user=_user_prompt(question, raw_text),
        model_cls=model_cls,
        session_id=session_id,
    )
    if result is None or result.option_id == UNCLEAR:
        return None
    return result.option_id


def _direct_match(question: Question, raw_text: str) -> str | None:
    """Дешёвая проверка до обращения к модели.

    Три шага: точное совпадение с подписью или id, явное «не знаю» и совпадение
    по основам слов. Модель вызывается только если ничего не сошлось.
    """
    normalized = raw_text.strip().casefold()
    for option in question.options:
        if normalized in (option.id.casefold(), option.label.casefold()):
            return option.id

    option_ids = question.option_ids()
    if normalized in DONT_KNOW and UNKNOWN_OPTION in option_ids:
        return UNKNOWN_OPTION

    answer_tokens = tokens(raw_text)
    if not answer_tokens:
        return None

    # Побеждает вариант, чья подпись целиком содержится в ответе и который
    # при этом единственный: «хромаю» не должно выбирать между двумя похожими.
    matches = [
        option.id
        for option in question.options
        if (label := tokens(option.label)) and label <= answer_tokens
    ]
    return matches[0] if len(matches) == 1 else None
