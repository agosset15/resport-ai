"""Сокращение опроса: один экстренный скринер вместо каскада и чистка лишних вопросов.

Зачем: до правки в каждом сценарии задавалось 24–25 вопросов, на благополучном пути —
21–23. Среди них были нерелевантные: сценарий травмы пальца спрашивал про отёк одной
ноги, одышку и боль в груди (вопрос `g_dvt`).

Что делает скрипт:

    g_alarm          новый первый экстренный скринер: «есть ли сейчас что-то из этого?»
    g_deformity      \\
    g_circulation     |  задаются только при g_alarm = present | unknown
    g_pain_swelling   |  (ответ «не знаю» тоже раскрывает каскад — иначе человек
    g_hot_joint       |   пропустил бы все проверки безопасности вместе с red flags)
    g_dvt            /
    g_sleep          удаляется: единственное его правило ушло в самостоятельное
                     восстановление, на маршрут вопрос больше не влияет
    g_dvt            удаляется целиком в сценариях кисти и пальца: признаки ТГВ/ТЭЛА
                     к этой области не относятся
    home_*           длинные конъюнкции на ~25 условий заменяются короткими правилами

Почему конъюнкции обязательно переписать: `evaluate_condition` считает неотвеченный
вопрос несовпадением, поэтому правило, требующее `g_deformity: absent`, становится
невыполнимым для всех, кто ответил `g_alarm: none` и не получил детальных вопросов.

    uv run python -m tools.trim --dry-run
    uv run python -m tools.trim
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from core.config import PROJECT_ROOT

DEFS_DIR = PROJECT_ROOT / "core" / "scenarios" / "defs"
REPORT_PATH = PROJECT_ROOT / "docs" / "trim_report.md"

GATED_QUESTIONS = ("g_deformity", "g_circulation", "g_pain_swelling", "g_hot_joint", "g_dvt")
GATE_CONDITION = "    ask_if: {g_alarm: [present, unknown]}\n"

#: Вопросы, которые удаляются во всех сценариях.
DROP_ALWAYS = ("g_sleep",)

#: Вопросы, не относящиеся к области тела: ключ — область, значение — что убрать.
DROP_BY_REGION = {"hand_finger": ("g_dvt",)}

ALARM_QUESTION = """  # Единый экстренный скринер. Детальные вопросы ниже задаются только при
  # ответе «да» или «не знаю»: «не знаю» тоже обязано раскрывать каскад, иначе
  # вместе с вопросами будут пропущены и красные флаги.
  - key: g_alarm
    text: Есть ли сейчас что-то из перечисленного?
    hint: |-
      Заметная деформация или открытая рана; конечность холодная, бледная или синюшная;
      сильное онемение или нарастающая слабость; боль быстро и несоразмерно нарастает;
      сустав горячий и красный, есть температура или очень плохое самочувствие;
      необъяснимый отёк одной ноги, одышка или боль в груди.
    options:
    - {id: present, label: 'Да, что-то из этого есть'}
    - {id: none, label: 'Нет, ничего из этого'}
    - {id: unknown, label: Не знаю / не могу определить}

"""


@dataclass
class TrimReport:
    path: Path
    removed_questions: list[str] = field(default_factory=list)
    gated: list[str] = field(default_factory=list)
    removed_rules: int = 0
    rewritten_rules: list[str] = field(default_factory=list)
    removed_flags: list[str] = field(default_factory=list)
    questions_before: int = 0
    questions_after: int = 0


def section_bounds(lines: list[str], key: str) -> tuple[int, int]:
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"{key}:")
    for i in range(start + 1, len(lines)):
        if lines[i] and not lines[i][0].isspace() and not lines[i].startswith("#"):
            return start, i
    return start, len(lines)


def split_blocks(lines: list[str]) -> list[list[str]]:
    """Режет секцию на блоки «комментарии + элемент».

    Комментарий начинает новый блок: он относится к элементу НИЖЕ.
    """
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


def block_key(block: list[str], field_name: str) -> str | None:
    match = re.search(rf"^\s+-?\s*{field_name}: (\S+?)}}?$", "".join(block), re.MULTILINE)
    return match.group(1) if match else None


def body_region(lines: list[str]) -> str | None:
    for line in lines:
        if line.startswith("body_region:"):
            return line.split(":", 1)[1].strip()
    return None


def drop_refs(block: list[str], removed: set[str]) -> list[str]:
    """Убирает из ask_if ссылки на удалённые вопросы."""
    out: list[str] = []
    for line in block:
        stripped = line.strip()
        if stripped.startswith("- ") and ":" in stripped:
            ref = stripped[2:].split(":", 1)[0].strip()
            if ref in removed:
                continue
        out.append(line)
    return out


def add_gate(block: list[str]) -> list[str]:
    """Вставляет ask_if сразу после строки text/hint, до options."""
    if "ask_if:" in "".join(block):
        return block
    for i, line in enumerate(block):
        if line.startswith("    options:"):
            return [*block[:i], GATE_CONDITION, *block[i:]]
    return block


def process(path: Path) -> tuple[str, TrimReport]:
    report = TrimReport(path=path)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    region = body_region(lines)

    to_remove = set(DROP_ALWAYS)
    if region in DROP_BY_REGION:
        to_remove.update(DROP_BY_REGION[region])

    # --- вопросы ----------------------------------------------------------
    q_start, q_end = section_bounds(lines, "questions")
    blocks = split_blocks(lines[q_start + 1 : q_end])
    report.questions_before = sum(1 for b in blocks if block_key(b, "key"))

    kept_blocks: list[list[str]] = []
    for block in blocks:
        key = block_key(block, "key")
        if key in to_remove:
            report.removed_questions.append(key or "?")
            continue
        block = drop_refs(block, to_remove)
        if key in GATED_QUESTIONS:
            block = add_gate(block)
            report.gated.append(key or "?")
        kept_blocks.append(block)

    # Скринер встаёт перед первым из детальных вопросов: условие ask_if ссылается
    # только назад, иначе загрузчик справедливо отвергнет сценарий.
    insert_at = next(
        (i for i, b in enumerate(kept_blocks) if block_key(b, "key") in GATED_QUESTIONS),
        None,
    )
    if insert_at is not None and "key: g_alarm" not in "".join(lines):
        kept_blocks.insert(insert_at, [ALARM_QUESTION])

    report.questions_after = sum(1 for b in kept_blocks if block_key(b, "key"))
    new_questions = [line for block in kept_blocks for line in block]

    # --- red flags --------------------------------------------------------
    new_flags: list[str] = []
    if any(line.rstrip() == "red_flags:" for line in lines):
        f_start, f_end = section_bounds(lines, "red_flags")
        for block in split_blocks(lines[f_start + 1 : f_end]):
            question = block_key(block, "question")
            if question in to_remove:
                report.removed_flags.append(block_key(block, "id") or "?")
                continue
            new_flags.append("".join(block))
        flags_header: list[str] = [lines[f_start]]
    else:
        f_start = f_end = -1
        flags_header = []

    # --- routing ----------------------------------------------------------
    r_start, r_end = section_bounds(lines, "routing")
    new_routing: list[str] = []
    dropped_plans: set[str] = set()
    for block in split_blocks(lines[r_start + 1 : r_end]):
        text = "".join(block)
        reason = block_key(block, "reason_code")

        # короткая конъюнкция вместо проверки всех ответов разом
        if reason == "home_prescribed_program":
            plan = block_key(block, "plan")
            new_routing.append(
                "  # Д: диагноз этого эпизода есть, программа назначена специалистом\n"
                "  - when:\n"
                "      all:\n"
                "      - {g_prior_eval: this_episode}\n"
                "      - {g_program: ready}\n"
                "    outcome: recovery_plan\n"
                f"    plan: {plan}\n"
                "    reason_code: home_prescribed_program\n"
            )
            report.rewritten_rules.append(reason)
            continue

        # наблюдение 48-72 ч покрывается планом self_rehab_basic из default-правила
        if reason == "home_observation":
            plan = block_key(block, "plan")
            if plan:
                dropped_plans.add(plan)
            report.removed_rules += 1
            continue

        if any(re.search(rf"\b{q}\b", text) for q in to_remove):
            if reason:
                report.removed_rules += 1
                continue
            block = drop_refs(block, to_remove)
        new_routing.append("".join(block))

    # --- plans ------------------------------------------------------------
    p_start, p_end = section_bounds(lines, "plans")
    plan_lines = lines[p_start + 1 : p_end]
    new_plans: list[str] = []
    skipping = False
    for line in plan_lines:
        is_plan_key = re.match(r"^  (\S+):\s*$", line)
        if is_plan_key:
            skipping = is_plan_key.group(1) in dropped_plans
        if not skipping:
            new_plans.append(line)

    rest = lines[p_end:]
    head = lines[:q_start]

    body = [
        lines[q_start],
        *new_questions,
        *flags_header,
        *new_flags,
        lines[r_start],
        *new_routing,
        lines[p_start],
        *new_plans,
        *rest,
    ]
    return "".join([*head, *body]), report


def render_report(reports: list[TrimReport]) -> str:
    lines = [
        "# Отчёт о сокращении опроса",
        "",
        "Сгенерирован `tools/trim.py`. **Требует ревью врача до беты.**",
        "",
        "Детальные вопросы безопасности сохранены полностью, но задаются после единого",
        "скринера `g_alarm`. Ответ «не знаю» на скринер раскрывает весь каскад, поэтому",
        "чувствительность к красным флагам не падает у тех, кто не уверен.",
        "",
        "| сценарий | вопросов до | после | под скринером | удалено | правил убрано |",
        "|---|---|---|---|---|---|",
    ]
    for r in sorted(reports, key=lambda x: x.path.name):
        lines.append(
            f"| {r.path.name} | {r.questions_before} | {r.questions_after} | "
            f"{len(r.gated)} | {', '.join(r.removed_questions) or '—'} | {r.removed_rules} |"
        )
    removed_flags = [f for r in reports for f in r.removed_flags]
    lines += [
        "",
        "## Удалённые red flags",
        "",
        "Удаляются только вместе со своим вопросом — там, где он не относится к области тела:",
        "",
    ]
    lines += [f"- `{f}`" for f in sorted(set(removed_flags))] or ["- нет"]
    lines += [
        "",
        "## Переписанные правила",
        "",
        "`home_prescribed_program` — вместо конъюнкции на ~25 условий короткая проверка",
        "«есть диагноз этого эпизода и назначена программа». Маршрутизация упорядочена,",
        "поэтому до этого правила доходят только те, кто не задел ни одного правила выше:",
        "перечислять все безопасные ответы заново было избыточно, а после появления",
        "скринера стало ещё и невыполнимо.",
        "",
        "`home_observation` — правило и план удалены: наблюдение 48–72 часа покрывает план",
        "`self_rehab_basic`, который выдаёт default-правило.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Сокращение опроса")
    parser.add_argument("--dry-run", action="store_true", help="не записывать файлы")
    args = parser.parse_args()

    reports: list[TrimReport] = []
    for path in sorted(DEFS_DIR.rglob("*.yaml")):
        text, report = process(path)
        reports.append(report)
        if not args.dry_run:
            path.write_text(text, encoding="utf-8")
        print(
            f"{path.name:<42} {report.questions_before} -> {report.questions_after}, "
            f"правил убрано {report.removed_rules}" + ("  (dry-run)" if args.dry_run else "")
        )

    if not args.dry_run:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_report(reports), encoding="utf-8")
        print(f"\nОтчёт: {REPORT_PATH}")


if __name__ == "__main__":
    main()
