"""Анкета перед подбором БАДов и профиль пользователя.

Вопросы заданы кодом, а не YAML: их набор фиксирован ТЗ, и каждый ответ напрямую
управляет логикой подбора (`matcher.py`). Данные-за-данными здесь дали бы только
лишний слой — в отличие от сценариев, где содержание меняет врач без правки кода.

Порядок вопросов важен: возраст первым, потому что несовершеннолетним автоматический
подбор не делается вообще и остальные вопросы уже не нужны.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Field(StrEnum):
    AGE = "age"
    ALLERGIES = "allergies"
    CONDITIONS = "conditions"
    MEDICATIONS = "medications"
    OTHER_SUPPLEMENTS = "other_supplements"
    PREGNANT = "pregnant"
    BREASTFEEDING = "breastfeeding"
    UPCOMING_SURGERY = "upcoming_surgery"


class AnswerKind(StrEnum):
    NUMBER = "number"
    #: Список своими словами; «нет» превращается в пустой список.
    FREE_LIST = "free_list"
    YES_NO = "yes_no"


@dataclass(frozen=True, slots=True)
class Question:
    key: Field
    text: str
    kind: AnswerKind
    hint: str | None = None
    #: Вопрос задаётся, только если на эти поля уже ответили «да»/непусто.
    skip_if_none: bool = False


QUESTIONS: tuple[Question, ...] = (
    Question(
        key=Field.AGE,
        text="Сколько тебе полных лет?",
        kind=AnswerKind.NUMBER,
        hint="Автоматический подбор добавок доступен только совершеннолетним.",
    ),
    Question(
        key=Field.ALLERGIES,
        text="Есть ли аллергии? Перечисли через запятую.",
        kind=AnswerKind.FREE_LIST,
        hint="Если нет — напиши «нет».",
    ),
    Question(
        key=Field.CONDITIONS,
        text="Есть ли заболевания, о которых знаешь? Перечисли через запятую.",
        kind=AnswerKind.FREE_LIST,
        hint="Если нет — напиши «нет».",
    ),
    Question(
        key=Field.MEDICATIONS,
        text="Принимаешь ли лекарства? Перечисли через запятую.",
        kind=AnswerKind.FREE_LIST,
        hint="Важно для проверки взаимодействий. Если нет — напиши «нет».",
    ),
    Question(
        key=Field.OTHER_SUPPLEMENTS,
        text="Принимаешь ли другие добавки? Перечисли через запятую.",
        kind=AnswerKind.FREE_LIST,
        hint="Нужно, чтобы не удвоить один и тот же компонент. Если нет — «нет».",
    ),
    Question(
        key=Field.PREGNANT,
        text="Беременность?",
        kind=AnswerKind.YES_NO,
    ),
    Question(
        key=Field.BREASTFEEDING,
        text="Грудное вскармливание?",
        kind=AnswerKind.YES_NO,
    ),
    Question(
        key=Field.UPCOMING_SURGERY,
        text="Планируется ли операция?",
        kind=AnswerKind.YES_NO,
    ),
)

NO_WORDS = frozenset({"нет", "не", "-", "–", "никаких", "ничего", "нету", "no", "none"})


def parse_list(raw: str) -> tuple[str, ...]:
    """«нет» — это пустой список, а не элемент списка."""
    cleaned = raw.strip()
    if cleaned.casefold() in NO_WORDS:
        return ()
    parts = [part.strip(" .;") for part in cleaned.replace(";", ",").split(",")]
    return tuple(part for part in parts if part and part.casefold() not in NO_WORDS)


@dataclass(frozen=True, slots=True)
class SupplementProfile:
    """Ответы анкеты. `None` означает «не спрашивали или не ответил»."""

    age: int | None = None
    allergies: tuple[str, ...] = ()
    conditions: tuple[str, ...] = ()
    medications: tuple[str, ...] = ()
    other_supplements: tuple[str, ...] = ()
    pregnant: bool | None = None
    breastfeeding: bool | None = None
    upcoming_surgery: bool | None = None
    #: Ответы, на которые пользователь не ответил: профиль считается неполным.
    missing: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_complete(self) -> bool:
        return not self.missing

    def to_answers(self) -> dict[str, Any]:
        return {
            Field.AGE.value: self.age,
            Field.ALLERGIES.value: list(self.allergies),
            Field.CONDITIONS.value: list(self.conditions),
            Field.MEDICATIONS.value: list(self.medications),
            Field.OTHER_SUPPLEMENTS.value: list(self.other_supplements),
            Field.PREGNANT.value: self.pregnant,
            Field.BREASTFEEDING.value: self.breastfeeding,
            Field.UPCOMING_SURGERY.value: self.upcoming_surgery,
        }

    @classmethod
    def from_answers(cls, answers: dict[str, Any]) -> SupplementProfile:
        def as_list(key: Field) -> tuple[str, ...]:
            value = answers.get(key.value) or []
            if isinstance(value, str):
                return parse_list(value)
            return tuple(str(item) for item in value)

        def as_bool(key: Field) -> bool | None:
            value = answers.get(key.value)
            return bool(value) if isinstance(value, bool) else None

        age_raw = answers.get(Field.AGE.value)
        age = (
            int(age_raw)
            if isinstance(age_raw, int | float | str) and str(age_raw).isdigit()
            else None
        )

        missing = [
            key.value
            for key in (Field.PREGNANT, Field.BREASTFEEDING, Field.UPCOMING_SURGERY)
            if as_bool(key) is None
        ]
        if age is None:
            missing.insert(0, Field.AGE.value)

        return cls(
            age=age,
            allergies=as_list(Field.ALLERGIES),
            conditions=as_list(Field.CONDITIONS),
            medications=as_list(Field.MEDICATIONS),
            other_supplements=as_list(Field.OTHER_SUPPLEMENTS),
            pregnant=as_bool(Field.PREGNANT),
            breastfeeding=as_bool(Field.BREASTFEEDING),
            upcoming_surgery=as_bool(Field.UPCOMING_SURGERY),
            missing=tuple(missing),
        )
