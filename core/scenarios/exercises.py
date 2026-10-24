"""Загрузка и валидация библиотеки упражнений.

Вызывается один раз на старте процесса, как и загрузка сценариев: ошибка в данных
роняет процесс, а не всплывает посреди плана у пользователя.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from core.domain.exercise import Dosage, Exercise, ExerciseLibrary

SCHEMA_PATH = Path(__file__).parent / "library" / "schema.exercise.json"
DEFAULT_LIBRARY_PATH = Path(__file__).parent / "library" / "exercises.yaml"


class ExerciseValidationError(Exception):
    """Библиотека не прошла валидацию. Сообщение содержит все найденные проблемы."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(
            "Ошибки в библиотеке упражнений:\n" + "\n".join(f"  - {e}" for e in errors)
        )


def _load_schema() -> Draft202012Validator:
    with SCHEMA_PATH.open(encoding="utf-8") as fh:
        return Draft202012Validator(json.load(fh))


def _as_dosage(raw: dict[str, Any]) -> Dosage:
    return Dosage(
        sets=raw.get("sets"),
        reps=raw.get("reps"),
        duration_seconds=raw.get("duration_seconds"),
        note=raw.get("note"),
    )


def _as_exercise(raw: dict[str, Any]) -> Exercise:
    return Exercise(
        id=raw["id"],
        title=raw["title"],
        instruction=raw["instruction"],
        dosage=_as_dosage(raw["dosage"]),
        body_region=raw["body_region"],
        phase=raw["phase"],
        limits=tuple(raw.get("limits", [])),
        equipment=tuple(raw.get("equipment", [])),
        lookup_hint=raw.get("lookup_hint"),
        source=raw.get("source"),
        review_status=raw.get("review_status", "draft"),
        updated_at=raw.get("updated_at"),
    )


def _validate_semantics(exercises: list[Exercise]) -> list[str]:
    errors: list[str] = []

    ids = [e.id for e in exercises]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        errors.append(f"дублирующиеся id упражнений: {sorted(duplicates)}")

    for exercise in exercises:
        dosage = exercise.dosage
        # Иначе карточка покажет «по самочувствию» там, где нужна конкретика:
        # бот не придумывает дозировки сам, значит они обязаны быть в данных.
        if dosage.duration_seconds is None and dosage.reps is None and not dosage.note:
            errors.append(f"{exercise.id}: в dosage нужны reps, duration_seconds или хотя бы note")
        if dosage.duration_seconds is not None and dosage.reps is not None:
            errors.append(
                f"{exercise.id}: dosage задаёт и повторения, и длительность — выбери одно"
            )
        if not exercise.limits:
            errors.append(f"{exercise.id}: не указаны limits — ограничения обязательны")

    return errors


def load_library(path: Path | None = None) -> ExerciseLibrary:
    path = path or DEFAULT_LIBRARY_PATH
    validator = _load_schema()

    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ExerciseValidationError([f"{path.name}: файл пуст или не является объектом"])

    schema_errors = [
        f"{path.name}: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in validator.iter_errors(raw)
    ]
    if schema_errors:
        raise ExerciseValidationError(schema_errors)

    exercises = [_as_exercise(item) for item in raw["exercises"]]
    semantic_errors = _validate_semantics(exercises)
    if semantic_errors:
        raise ExerciseValidationError(semantic_errors)

    return ExerciseLibrary(exercises={e.id: e for e in exercises})
