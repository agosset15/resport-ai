"""Пересборка маршрутизации сценариев в тиры срочности.

Зачем: до этой правки в каждом сценарии все routing-правила вели к `refer_specialist`,
а единственный путь к плану требовал конъюнкции ~25 идеальных ответов и назначения врача.
Случайный прогон давал 99.9% направлений к специалисту — бот не вёл даже лёгкие травмы.

Что делает скрипт:

    red_flags            не трогаются никогда (экстренные признаки)
    today_*              остаются refer_specialist (нужен осмотр в этот день)
    planned_*            из DEMOTE_PLANNED  -> self_rehab + план self_rehab_guarded
    unclear_*            из DEMOTE_UNCLEAR  -> правило удаляется (падает в default)
    default              -> self_rehab + план self_rehab_basic
    home_*               не трогаются (восстановление по назначению специалиста)

Принцип безопасности: понижается только то, что перечислено явно. Любой незнакомый
reason_code остаётся направлением к специалисту, поэтому новый сценарий не может
случайно оказаться в самостоятельном восстановлении.

    uv run python -m tools.retier --dry-run      # показать, что изменится
    uv run python -m tools.retier                # записать и собрать отчёт

Отчёт docs/retier_report.md — предмет ревью врача: в нём каждое изменённое правило.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

from core.config import PROJECT_ROOT

DEFS_DIR = PROJECT_ROOT / "core" / "scenarios" / "defs"
REPORT_PATH = PROJECT_ROOT / "docs" / "retier_report.md"

# Правила «к врачу планово», которые становятся самостоятельным восстановлением
# под наблюдением. Суффикс — это ключ вопроса, давшего правило.
DEMOTE_PLANNED = frozenset(
    {
        # общие: стойкие умеренные симптомы без тревожных признаков
        "g_trend",
        "g_pain_swelling",
        "g_history",
        "g_sleep",
        "g_program",
        # голеностоп
        "a_course",
        "a_swelling",
        "a_instability",
        # приводящие
        "ad_location",
        "ad_onset",
        "ad_recurrence",
        "ad_walk",
        # палец
        "f_course",
        "f_which",
        # задняя поверхность бедра
        "h_location",
        "h_moment",
        "h_recurrence",
        "h_walk",
        # колено (пателлофеморальная боль)
        "pf_location",
        "pf_load_response",
        "pf_onset",
        "pf_when",
        # связка надколенника
        "pt_location",
        "pt_progression",
        "pt_trigger",
        "pt_warmup",
        # передняя поверхность бедра
        "qd_location",
        "qd_mechanism",
        "qd_relapse",
        "qd_walk",
    }
)

# Ответы «не знаю», на которых больше не нужно направление к врачу: это вопросы
# про обстоятельства и анамнез, а не про наблюдаемый опасный признак.
DEMOTE_UNCLEAR = frozenset(
    {
        "g_comorbid",
        "g_help_access",
        "g_history",
        "g_prior_eval",
        "g_program",
        "g_sleep",
        "a_course",
        "a_mechanism",
        "ad_location",
        "ad_onset",
        "ad_recurrence",
        "f_course",
        "f_mechanism",
        "f_pinch",
        "f_which",
        "h_location",
        "h_moment",
        "h_recurrence",
        "pf_location",
        "pf_load_response",
        "pf_onset",
        "pf_when",
        "pt_location",
        "pt_onset",
        "pt_progression",
        "pt_trigger",
        "pt_warmup",
        "qd_location",
        "qd_mechanism",
        "qd_relapse",
    }
)

# Область тела: отбор общих вопросов и выбор картинки зоны боли.
BODY_REGIONS = {
    "ankle_sprain": "ankle_foot",
    "finger_sprain": "hand_finger",
    "hamstring_strain": "thigh_back",
    "quadriceps_strain": "thigh_front",
    "adductor_strain": "groin",
    "patellar_tendinopathy": "knee",
    "patellofemoral_pain": "knee",
    "patellar_pain": "knee",
}

PLAN_BASIC = """  self_rehab_basic:
    title: Самостоятельное восстановление
    completion_text: |
      Программа пройдена. Это не вывод о полном выздоровлении и не допуск к тренировкам:
      возврат к бегу, прыжкам, смене направления и контакту оценивает специалист.
      Если боль вернулась или прогресс остановился — покажись врачу.
    stages:
    - key: relief
      title: Первые дни — снять нагрузку
      days: 3
      description: Бытовая активность в комфортных пределах и ежедневная оценка.
      tasks:
      - {key: comfort_activity, text: 'Обычные бытовые дела в комфортных пределах — без тренировок, бега и игры'}
      - {key: no_self_tests, text: 'Не проверять травму прыжками, нажатием и растяжкой'}
      - {key: morning_check, text: 'Утром отметить боль (0–10), отёк и как даётся обычная нагрузка'}
      advance_if: {feeling: better, consecutive: 2, min_days: 2}
      escalate_if: {feeling: worse, consecutive: 2}
    - key: load_return
      title: Постепенное возвращение нагрузки
      days: 7
      description: Добавляем нагрузку маленькими шагами и смотрим на реакцию к утру.
      tasks:
      - {key: daily_activity, text: 'Полный объём бытовой активности — в пределах, где нет боли'}
      - {key: gradual_load, text: 'Добавлять нагрузку маленькими шагами: больно или хуже к утру — шаг назад'}
      - {key: no_sport_yet, text: 'Без тренировок, игры, прыжков и смены направления'}
      - {key: morning_check, text: 'Утром отметить боль (0–10), отёк и как даётся нагрузка'}
      advance_if: {feeling: better, consecutive: 3, tasks_done_ratio_gte: 0.7}
      escalate_if: {feeling: worse, consecutive: 2}
"""

PLAN_GUARDED = """  self_rehab_guarded:
    title: Самостоятельное восстановление под наблюдением
    completion_text: |
      Период наблюдения пройден. Это не диагноз и не допуск к тренировкам.
      По твоим ответам были стойкие симптомы, поэтому покажись специалисту,
      прежде чем возвращаться к спорту.
    stages:
    - key: guarded_watch
      title: Осторожное наблюдение
      days: 7
      description: Нагрузку не наращиваем, следим за динамикой каждый день.
      tasks:
      - {key: comfort_activity, text: 'Только бытовая активность в комфортных пределах — без тренировок и игры'}
      - {key: no_self_tests, text: 'Не проверять травму прыжками, нажатием и растяжкой'}
      - {key: morning_check, text: 'Утром отметить боль (0–10), отёк и как даётся обычная нагрузка'}
      - {key: note_change, text: 'Записать, если появился новый признак: онемение, деформация, температура, рост отёка'}
      advance_if: {feeling: better, consecutive: 3, min_days: 3}
      escalate_if:
        feeling: [same, worse]
        consecutive: 2
"""

SELF_REHAB_TEXT = """  self_rehab_intro: |
    Тревожных признаков в твоих ответах нет. Это не диагноз и не допуск к тренировкам.
    Дальше — короткий план: каждый день отмечаешь задачи и самочувствие.
    Гарантий я не даю: травму я не осматривал. Если станет хуже, появится онемение,
    деформация, холодная или синюшная кожа, резко вырастет отёк или за несколько дней
    не станет легче — останови план и покажись врачу.
"""

DEFAULT_RULE = """  # D: тревожных признаков нет — ведём самостоятельное восстановление
  - default: true
    outcome: self_rehab
    plan: self_rehab_basic
    reason_code: default_self_rehab
"""


@dataclass
class Change:
    reason_code: str
    action: str
    note: str = ""


@dataclass
class FileReport:
    path: Path
    version_from: int = 0
    version_to: int = 0
    changes: list[Change] = field(default_factory=list)
    kept: int = 0
    plans_used: set[str] = field(default_factory=set)


def split_routing_blocks(lines: list[str]) -> list[list[str]]:
    """Режет секцию на блоки «комментарии + элемент».

    Комментарий начинает новый блок: он относится к правилу НИЖЕ, а не к предыдущему.
    Иначе при перестановке правил медицинские аннотации («# С: ...») оказываются над
    чужими правилами — а это именно то, что читает врач на ревью.
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


def section_bounds(lines: list[str], key: str) -> tuple[int, int]:
    """Границы секции верхнего уровня: от строки `key:` до следующего ключа."""
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"{key}:")
    for i in range(start + 1, len(lines)):
        if lines[i] and not lines[i][0].isspace() and not lines[i].startswith("#"):
            return start, i
    return start, len(lines)


def retier_block(block: list[str], report: FileReport) -> list[str] | None:
    """Новое содержимое блока или None, если правило нужно удалить."""
    text = "".join(block)

    if re.search(r"^\s*-\s*\{?default:", text, re.MULTILINE):
        report.changes.append(
            Change("default_referral", "default -> self_rehab", "план self_rehab_basic")
        )
        report.plans_used.add("self_rehab_basic")
        return [DEFAULT_RULE]

    match = re.search(r"^\s+reason_code: (\S+?)}?$", text, re.MULTILINE)
    if match is None:
        report.kept += 1
        return block
    reason = match.group(1)

    prefix, _, suffix = reason.partition("_")

    if prefix == "unclear" and suffix in DEMOTE_UNCLEAR:
        report.changes.append(Change(reason, "удалено", "ответ «не знаю» больше не ведёт к врачу"))
        return None

    if prefix == "planned" and suffix in DEMOTE_PLANNED:
        new_lines: list[str] = []
        for line in block:
            if line.strip() == "outcome: refer_specialist":
                indent = line[: len(line) - len(line.lstrip())]
                new_lines.append(f"{indent}outcome: self_rehab\n")
                new_lines.append(f"{indent}plan: self_rehab_guarded\n")
            elif line.strip() == f"reason_code: {reason}":
                indent = line[: len(line) - len(line.lstrip())]
                new_lines.append(f"{indent}reason_code: watch_{suffix}\n")
            else:
                new_lines.append(line)
        report.changes.append(
            Change(reason, f"planned -> self_rehab (watch_{suffix})", "план self_rehab_guarded")
        )
        report.plans_used.add("self_rehab_guarded")
        return new_lines

    report.kept += 1
    return block


def process(path: Path) -> tuple[str, FileReport]:
    report = FileReport(path=path)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    # 1. routing
    r_start, r_end = section_bounds(lines, "routing")
    blocks = split_routing_blocks(lines[r_start + 1 : r_end])
    new_routing: list[str] = []
    for block in blocks:
        result = retier_block(block, report)
        if result is not None:
            new_routing.extend(result)

    # 2. plans: добавляем планы самостоятельного восстановления
    p_start, p_end = section_bounds(lines, "plans")
    new_plans = lines[p_start + 1 : p_end]
    existing = "".join(new_plans)
    for plan_key, block_text in (
        ("self_rehab_basic", PLAN_BASIC),
        ("self_rehab_guarded", PLAN_GUARDED),
    ):
        if plan_key in report.plans_used and f"{plan_key}:" not in existing:
            new_plans = [*new_plans, block_text]

    # 3. texts: преамбула самостоятельного восстановления
    t_start, t_end = section_bounds(lines, "texts")
    new_texts = lines[t_start + 1 : t_end]
    if "self_rehab_intro:" not in "".join(new_texts):
        new_texts = [*new_texts, SELF_REHAB_TEXT]

    head = lines[:r_start]

    # 4. version и body_region в шапке
    out_head: list[str] = []
    for line in head:
        version_match = re.match(r"^version: (\d+)\s*$", line)
        if version_match:
            old = int(version_match.group(1))
            report.version_from, report.version_to = old, old + 1
            out_head.append(f"version: {old + 1}\n")
            continue
        out_head.append(line)

    scenario_key = path.stem.split(".")[-1]
    region = BODY_REGIONS.get(scenario_key)
    if region and "body_region:" not in "".join(out_head):
        for i, line in enumerate(out_head):
            if line.startswith("entry_hints:"):
                out_head.insert(i, f"body_region: {region}\n")
                break

    assert p_start > r_end - 1, f"{path.name}: ожидался порядок routing -> plans -> texts"
    body = [
        lines[r_start],
        *new_routing,
        lines[p_start],
        *new_plans,
        lines[t_start],
        *new_texts,
    ]
    return "".join([*out_head, *body]), report


def render_report(reports: list[FileReport]) -> str:
    lines = [
        "# Отчёт о пересборке маршрутизации",
        "",
        "Сгенерирован `tools/retier.py`. **Требует ревью врача до беты.**",
        "",
        "Красные флаги (`rf_emergency_*`) и правила «к врачу сегодня» (`today_*`) не менялись.",
        "Понижены только правила из явных списков `DEMOTE_PLANNED` и `DEMOTE_UNCLEAR`;",
        "любой другой `reason_code` остался направлением к специалисту.",
        "",
    ]
    total_demoted = sum(1 for r in reports for c in r.changes if c.action.startswith("planned"))
    total_removed = sum(1 for r in reports for c in r.changes if c.action == "удалено")
    lines += [
        f"- сценариев изменено: {len(reports)}",
        f"- правил `planned_*` переведено в самостоятельное восстановление: {total_demoted}",
        f"- правил `unclear_*` удалено: {total_removed}",
        f"- правил оставлено без изменений: {sum(r.kept for r in reports)}",
        "",
    ]
    for r in sorted(reports, key=lambda x: x.path.name):
        lines += [
            f"## {r.path.name}  (version {r.version_from} → {r.version_to})",
            "",
            "| reason_code | что сделано | примечание |",
            "|---|---|---|",
        ]
        for c in r.changes:
            lines.append(f"| `{c.reason_code}` | {c.action} | {c.note} |")
        lines += ["", f"Без изменений: {r.kept} правил.", ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Пересборка маршрутизации в тиры")
    parser.add_argument("--dry-run", action="store_true", help="не записывать файлы")
    args = parser.parse_args()

    reports: list[FileReport] = []
    for path in sorted(DEFS_DIR.rglob("*.yaml")):
        text, report = process(path)
        reports.append(report)
        if not args.dry_run:
            path.write_text(text, encoding="utf-8")
        print(
            f"{path.name:<42} изменено {len(report.changes):>3}, оставлено {report.kept:>3}"
            + ("  (dry-run)" if args.dry_run else "")
        )

    if not args.dry_run:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(render_report(reports), encoding="utf-8")
        print(f"\nОтчёт: {REPORT_PATH}")


if __name__ == "__main__":
    main()
