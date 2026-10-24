"""Загрузка и валидация базы БАДов.

Как и сценарии, база грузится один раз на старте: битая запись роняет процесс, а не
всплывает у пользователя в карточке.

Главная семантическая проверка: запись нельзя перевести в `approved`, пока в полях
приёма стоит маркер «НЕ ЗАПОЛНЕНО». Иначе бот покажет дозировку, которой никто не
проверял, — ровно то, что ТЗ запрещает.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from core.domain.supplement import (
    UNFILLED,
    Component,
    Intake,
    Interaction,
    Source,
    Supplement,
    SupplementRegistry,
)

SCHEMA_PATH = Path(__file__).with_name("schema.json")
DEFAULT_DEFS_DIR = Path(__file__).parent / "defs"


class SupplementValidationError(Exception):
    """База не прошла валидацию. Сообщение содержит все найденные проблемы."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Ошибки в базе БАДов:\n" + "\n".join(f"  - {e}" for e in errors))


def _load_schema() -> Draft202012Validator:
    with SCHEMA_PATH.open(encoding="utf-8") as fh:
        return Draft202012Validator(json.load(fh))


def _build(raw: dict[str, Any]) -> Supplement:
    intake_raw = raw["intake"]
    source_raw = raw["source"]
    return Supplement(
        id=raw["id"],
        product=raw["product"],
        manufacturer=raw["manufacturer"],
        composition=tuple(
            Component(name=item["name"], amount=item.get("amount"), unit=item.get("unit"))
            for item in raw["composition"]
        ),
        rationale=raw["rationale"],
        benefit_limits=raw["benefit_limits"],
        intake=Intake(dose_text=intake_raw["dose_text"], duration_text=intake_raw["duration_text"]),
        source=Source(
            title=source_raw["title"],
            url=source_raw["url"],
            retrieved_at=source_raw["retrieved_at"],
        ),
        updated_at=raw["updated_at"],
        excipients=tuple(raw.get("excipients", [])),
        allergens=tuple(raw.get("allergens", [])),
        contraindications=tuple(raw.get("contraindications", [])),
        side_effects=tuple(raw.get("side_effects", [])),
        interactions=tuple(
            Interaction(with_what=item["with_what"], note=item["note"])
            for item in raw.get("interactions", [])
        ),
        adverse_reaction_actions=raw.get("adverse_reaction_actions", ""),
        min_age=int(raw.get("min_age", 18)),
        review_status=raw.get("review_status", "draft"),
    )


def _validate_semantics(supplement: Supplement) -> list[str]:
    errors: list[str] = []
    sid = supplement.id

    if supplement.review_status == "approved":
        if not supplement.intake.is_filled:
            errors.append(
                f"{sid}: запись нельзя подписать (approved), пока в приёме стоит "
                f"«{UNFILLED}» — бот не придумывает дозировки"
            )
        if not supplement.adverse_reaction_actions:
            errors.append(
                f"{sid}: подписанная запись обязана описывать действия при нежелательной реакции"
            )
        if not supplement.contraindications:
            errors.append(f"{sid}: подписанная запись обязана перечислять противопоказания")

    if supplement.min_age < 18:
        errors.append(f"{sid}: автоматический подбор доступен только совершеннолетним")

    names = [component.name.strip().casefold() for component in supplement.composition]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        errors.append(f"{sid}: компонент указан дважды: {sorted(duplicates)}")

    return errors


def load_supplements(defs_dir: Path | None = None) -> SupplementRegistry:
    defs_dir = defs_dir or DEFAULT_DEFS_DIR
    validator = _load_schema()
    files = sorted(path for path in defs_dir.rglob("*.yaml") if path.is_file())
    if not files:
        # Пустая база — рабочее состояние: подбор просто ничего не предложит.
        return SupplementRegistry(supplements={})

    supplements: dict[str, Supplement] = {}
    errors: list[str] = []
    for path in files:
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        if not isinstance(raw, dict):
            errors.append(f"{path.name}: файл пуст или не является объектом")
            continue

        schema_errors = [
            f"{path.name}: "
            f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
            for error in validator.iter_errors(raw)
        ]
        if schema_errors:
            errors.extend(schema_errors)
            continue

        supplement = _build(raw)
        errors.extend(_validate_semantics(supplement))
        if supplement.id in supplements:
            errors.append(f"Дублирующийся id БАДа: {supplement.id} ({path.name})")
            continue
        supplements[supplement.id] = supplement

    if errors:
        raise SupplementValidationError(errors)
    return SupplementRegistry(supplements=supplements)
