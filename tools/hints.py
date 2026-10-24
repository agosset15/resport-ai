"""Расширение entry_hints разговорными формулировками.

Зачем: подсказки содержали только клинические термины («растяжение связок голеностопа»),
а пользователи пишут иначе («подвернул ногу», «забил бедро», «выбил палец»). Подсказки
работают сразу в двух местах — в детерминированном подборе `core/scenarios/matching.py`
и в промпте классификатора, — поэтому это самая дешёвая правка точности распознавания.

    uv run python -m tools.hints --dry-run
    uv run python -m tools.hints
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from core.config import PROJECT_ROOT

DEFS_DIR = PROJECT_ROOT / "core" / "scenarios" / "defs"

EXTRA_HINTS: dict[str, tuple[str, ...]] = {
    "ankle_sprain": (
        "подвернул",
        "вывернул стопу",
        "подвернулась нога",
        "наступил на чужую ногу",
        "подвернул на ровном месте",
        "нога опухла в районе косточки",
        "больно наступать",
    ),
    "finger_sprain": (
        "выбил палец",
        "ушиб палец",
        "ударил палец",
        "попал мячом по пальцу",
        "палец распух",
        "палец не сгибается",
        "мизинец",
        "большой палец",
    ),
    "hamstring_strain": (
        "потянул заднюю",
        "задняя поверхность бедра",
        "прострелило сзади бедра",
        "дернуло под коленом сзади",
        "бицепс бедра",
        "потянул на спринте",
        "потянул на ускорении",
    ),
    "quadriceps_strain": (
        "забил бедро",
        "отбил бедро",
        "ударили в бедро",
        "передняя поверхность бедра",
        "квадрицепс",
        "потянул переднюю",
        "больно разгибать колено",
    ),
    "adductor_strain": (
        "потянул пах",
        "болит в паху",
        "дернуло в паху",
        "паховая область",
        "внутренняя поверхность бедра",
        "приводящая мышца",
        "больно после удара по мячу",
    ),
    "patellar_tendinopathy": (
        "болит под чашечкой",
        "болит под коленом",
        "связка надколенника",
        "колено болит от прыжков",
        "прыжковое колено",
        "больно приземляться",
    ),
    "patellofemoral_pain": (
        "болит вокруг чашечки",
        "болит за чашечкой",
        "колено болит на лестнице",
        "колено болит при приседаниях",
        "болит после долгого сидения",
        "колено бегуна",
        "хрустит колено",
    ),
}


def merge_hints(line: str, extra: tuple[str, ...]) -> tuple[str, int]:
    """Дополняет flow-список entry_hints, не трогая существующие подсказки."""
    match = re.match(r"^entry_hints: \[(.*)\]\s*$", line)
    assert match, f"неожиданный формат entry_hints: {line!r}"
    current = [part.strip() for part in match.group(1).split(",") if part.strip()]
    added = [hint for hint in extra if hint not in current]
    merged = current + added
    return f"entry_hints: [{', '.join(merged)}]\n", len(added)


def process(path: Path) -> tuple[str, int]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    key = path.stem.split(".")[-1]
    extra = EXTRA_HINTS.get(key)
    if extra is None:
        return "".join(lines), 0

    added_total = 0
    for i, line in enumerate(lines):
        if line.startswith("entry_hints:"):
            lines[i], added_total = merge_hints(line, extra)
            break
    return "".join(lines), added_total


def main() -> None:
    parser = argparse.ArgumentParser(description="Расширение entry_hints")
    parser.add_argument("--dry-run", action="store_true", help="не записывать файлы")
    args = parser.parse_args()

    for path in sorted(DEFS_DIR.rglob("*.yaml")):
        text, added = process(path)
        if added and not args.dry_run:
            path.write_text(text, encoding="utf-8")
        print(f"{path.name:<42} +{added} подсказок" + ("  (dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
