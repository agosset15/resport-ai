"""Вставка упражнений в этапы планов самостоятельного восстановления.

Планы `self_rehab_basic` и `self_rehab_guarded` появились в сценариях на первой фазе
с одними только задачами наблюдения. Здесь к их этапам добавляются ссылки на
упражнения из библиотеки — по области тела сценария.

Что в какой этап попадает, задаёт `EXERCISES_BY_REGION` в `tools/retier.py`: там же
лежат сами шаблоны планов, и держать подбор в двух местах нельзя. Содержание карточек
ревьюится врачом отдельно, в `core/scenarios/library/exercises.yaml`.

Скрипт идемпотентен: этап, у которого уже есть `exercises`, не трогается.

    uv run python -m tools.plan_exercises --dry-run
    uv run python -m tools.plan_exercises
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from core.config import PROJECT_ROOT
from tools.retier import BODY_REGIONS, EXERCISES_BY_REGION

DEFS_DIR = PROJECT_ROOT / "core" / "scenarios" / "defs"

#: stage.key -> какой набор упражнений брать из EXERCISES_BY_REGION
STAGE_SETS = {
    "relief": "acute",
    "guarded_watch": "acute",
    "load_return": "load_return",
}


def inject(lines: list[str], region: str) -> tuple[list[str], list[str]]:
    """Добавляет `exercises:` в этапы планов self_rehab. Возвращает (строки, что изменили)."""
    sets = EXERCISES_BY_REGION.get(region, {})
    if not sets:
        return lines, []

    out: list[str] = []
    touched: list[str] = []
    current_stage: str | None = None
    stage_has_exercises = False

    for line in lines:
        stage_match = re.match(r"^    - key: (\S+)\s*$", line)
        if stage_match:
            current_stage = stage_match.group(1)
            stage_has_exercises = False

        if line.strip().startswith("exercises:"):
            stage_has_exercises = True

        # advance_if закрывает описание этапа — вставляем прямо перед ним
        if (
            line.startswith("      advance_if:")
            and current_stage in STAGE_SETS
            and not stage_has_exercises
        ):
            ids = sets.get(STAGE_SETS[current_stage], ())
            if ids:
                out.append(f"      exercises: [{', '.join(ids)}]\n")
                touched.append(current_stage)

        out.append(line)

    return out, touched


def process(path: Path) -> tuple[str, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    region = next(
        (line.split(":", 1)[1].strip() for line in lines if line.startswith("body_region:")),
        None,
    )
    if region is None:
        region = BODY_REGIONS.get(path.stem.split(".")[-1], "")
    if not region:
        return "".join(lines), []

    new_lines, touched = inject(lines, region)
    return "".join(new_lines), touched


def main() -> None:
    parser = argparse.ArgumentParser(description="Упражнения в планы self_rehab")
    parser.add_argument("--dry-run", action="store_true", help="не записывать файлы")
    args = parser.parse_args()

    for path in sorted(DEFS_DIR.rglob("*.yaml")):
        text, touched = process(path)
        if touched and not args.dry_run:
            path.write_text(text, encoding="utf-8")
        print(
            f"{path.name:<42} этапов дополнено: {len(touched)} {touched or ''}"
            + ("  (dry-run)" if args.dry_run else "")
        )


if __name__ == "__main__":
    main()
