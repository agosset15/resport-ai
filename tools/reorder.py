"""Порядок правил маршрутизации: сначала безопасность, потом планы.

Зачем: пока все правила вели к специалисту, их порядок ничего не решал. После
пересборки тиров он стал критичным — `route()` берёт первое совпавшее правило,
поэтому правило самостоятельного восстановления, стоящее выше, перекрывает
направление к врачу, стоящее ниже.

Пример реальной ошибки, которую это чинит: `a_instability: p_unstable` (нестабильность
голеностопа, тир watch) стояло выше `g_comorbid: p_present` (заболевания, влияющие на
заживление, направление к врачу). Человек с обоими признаками получал план вместо
осмотра.

Скрипт переставляет правила по тирам, сохраняя относительный порядок внутри тира:

    1. refer_specialist   — сначала всё, что уводит к врачу
    2. recovery_plan      — восстановление по назначению специалиста
    3. self_rehab         — самостоятельное восстановление
    4. default            — всегда последним (требование загрузчика)

Инвариант закреплён проверкой в `core/scenarios/loader.py`, так что вручную его
сломать уже не получится.

    uv run python -m tools.reorder --dry-run
    uv run python -m tools.reorder
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from core.config import PROJECT_ROOT

DEFS_DIR = PROJECT_ROOT / "core" / "scenarios" / "defs"

TIER_ORDER = {"refer_specialist": 0, "recovery_plan": 1, "self_rehab": 2}


def section_bounds(lines: list[str], key: str) -> tuple[int, int]:
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"{key}:")
    for i in range(start + 1, len(lines)):
        if lines[i] and not lines[i][0].isspace() and not lines[i].startswith("#"):
            return start, i
    return start, len(lines)


def split_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        starts_item = line.startswith("  - ")
        starts_comment = line.startswith("  #")
        has_item = any(c.startswith("  - ") for c in current)
        if (starts_item or starts_comment) and has_item:
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def tier_of(block: list[str]) -> tuple[int, bool]:
    """(номер тира, это default-правило)."""
    text = "".join(block)
    is_default = bool(re.search(r"^\s*-\s*\{?default:", text, re.MULTILINE))
    match = re.search(r"^\s+outcome: (\S+?)}?$", text, re.MULTILINE)
    if match is None:
        match = re.search(r"outcome: ([a-z_]+)", text)
    outcome = match.group(1) if match else "refer_specialist"
    return TIER_ORDER.get(outcome, 0), is_default


def process(path: Path) -> tuple[str, int]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    start, end = section_bounds(lines, "routing")
    blocks = split_blocks(lines[start + 1 : end])

    decorated = [(tier_of(block), i, block) for i, block in enumerate(blocks)]
    # default — всегда последний; внутри тира сохраняем исходный порядок
    ordered = sorted(decorated, key=lambda item: (item[0][1], item[0][0], item[1]))
    moved = sum(1 for new, old in zip(ordered, decorated, strict=True) if new[1] != old[1])

    new_routing = [line for _, _, block in ordered for line in block]
    out = [*lines[: start + 1], *new_routing, *lines[end:]]
    return "".join(out), moved


def main() -> None:
    parser = argparse.ArgumentParser(description="Порядок правил маршрутизации по тирам")
    parser.add_argument("--dry-run", action="store_true", help="не записывать файлы")
    args = parser.parse_args()

    for path in sorted(DEFS_DIR.rglob("*.yaml")):
        text, moved = process(path)
        if not args.dry_run:
            path.write_text(text, encoding="utf-8")
        print(
            f"{path.name:<42} переставлено правил: {moved}"
            + ("  (dry-run)" if args.dry_run else "")
        )


if __name__ == "__main__":
    main()
