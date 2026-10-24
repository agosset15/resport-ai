"""Карточка упражнения и библиотека. Только данные, без I/O и без парсинга YAML.

Библиотека существует отдельно от сценариев по той же причине, что и сценарии отдельно
от кода: содержание ревьюит врач, а не программист. Этап плана ссылается на упражнения
по id, сами карточки лежат в одном месте и не дублируются по пятнадцати файлам.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

#: Фаза восстановления: чем раньше, тем меньше нагрузки.
PHASES = ("acute", "subacute", "return")

#: Область тела: совпадает с `body_region` сценария.
BODY_REGIONS = (
    "ankle_foot",
    "knee",
    "thigh_front",
    "thigh_back",
    "groin",
    "hand_finger",
    "general",
)

REVIEW_STATUSES = ("draft", "approved")


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Русское согласование: 1 подход, 2 подхода, 5 подходов."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return few
    return many


def _duration(seconds: int) -> str:
    if seconds >= 60 and seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} {_plural(minutes, 'минута', 'минуты', 'минут')}"
    return f"{seconds} {_plural(seconds, 'секунда', 'секунды', 'секунд')}"


@dataclass(frozen=True, slots=True)
class Dosage:
    """Дозировка: либо подходы с повторениями, либо длительность. Не одновременно."""

    sets: int | None = None
    reps: int | None = None
    duration_seconds: int | None = None
    note: str | None = None

    @property
    def is_timed(self) -> bool:
        return self.duration_seconds is not None

    def human(self) -> str:
        """Строка для карточки: «3 подхода по 12», «2 подхода по 30 секунд», «10 минут»."""
        parts: list[str] = []
        if self.is_timed:
            parts.append(_duration(self.duration_seconds or 0))
        elif self.reps:
            parts.append(
                f"{self.reps} {_plural(self.reps, 'повторение', 'повторения', 'повторений')}"
            )

        if self.sets and self.sets > 1 and parts:
            parts[0] = (
                f"{self.sets} {_plural(self.sets, 'подход', 'подхода', 'подходов')} по {parts[0]}"
            )

        if self.note:
            parts.append(self.note)
        return " — ".join(parts) if parts else "по самочувствию"


@dataclass(frozen=True, slots=True)
class Exercise:
    """То, что видит пользователь в карточке упражнения.

    `lookup_hint` — требование ТЗ: бот не показывает видео, а подсказывает, что
    упражнение стоит посмотреть в интернете по названию.
    """

    id: str
    title: str
    instruction: str
    dosage: Dosage
    body_region: str
    phase: str
    limits: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    lookup_hint: str | None = None
    source: str | None = None
    review_status: str = "draft"
    updated_at: str | None = None

    @property
    def needs_review(self) -> bool:
        return self.review_status != "approved"

    def lookup_text(self) -> str:
        return self.lookup_hint or f"Посмотри в интернете, как выглядит «{self.title}»."


@dataclass(frozen=True, slots=True)
class ExerciseLibrary:
    """Все загруженные упражнения. Строится один раз на старте процесса."""

    exercises: Mapping[str, Exercise]

    def get(self, exercise_id: str) -> Exercise | None:
        return self.exercises.get(exercise_id)

    def require(self, exercise_id: str) -> Exercise:
        exercise = self.exercises.get(exercise_id)
        if exercise is None:
            raise KeyError(f"Упражнение не найдено: {exercise_id}")
        return exercise

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.exercises))

    def for_region(self, body_region: str) -> tuple[Exercise, ...]:
        return tuple(
            e for e in self.exercises.values() if e.body_region in (body_region, "general")
        )

    def for_phase(self, body_region: str, phase: str) -> tuple[Exercise, ...]:
        return tuple(e for e in self.for_region(body_region) if e.phase == phase)

    def drafts(self) -> tuple[Exercise, ...]:
        """Упражнения без подписи врача — их перечисляет отчёт для ревью."""
        return tuple(e for e in self.exercises.values() if e.needs_review)
