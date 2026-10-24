"""Барьеры на боевых сценариях: маршрутизация не должна уехать обратно «всех к врачу».

До пересборки тиров случайный проход давал 99.9% направлений к специалисту, а
благополучный пользователь получал направление в 100% случаев после 21 вопроса.
Эти тесты фиксируют оба конца: бот ведёт лёгкие травмы сам и при этом не перестаёт
направлять к врачу по настоящим признакам.
"""

from __future__ import annotations

import random

import pytest

from core.domain.enums import Outcome
from core.domain.scenario import Scenario, ScenarioRegistry
from core.scenarios.engine import ScenarioEngine, TriageDecision
from core.scenarios.images import PAIN_POINT_IMAGES
from core.scenarios.loader import load_registry
from tests.conftest import PROD_DEFS_DIR

#: Ответы, которые обязаны вести к специалисту, даже если всё остальное спокойно.
#: Таблица написана руками по отчёту `docs/retier_report.md` и намеренно НЕ выводится
#: из YAML: выведенная из тех же данных, она не проверяла бы ничего.
MUST_REFER: tuple[tuple[str, str, str], ...] = (
    ("football.ankle_sprain", "g_deformity", "e_major"),
    ("football.ankle_sprain", "g_circulation", "e_color"),
    ("football.ankle_sprain", "g_circulation", "e_numb"),
    ("football.ankle_sprain", "g_pain_swelling", "e_disproportionate"),
    ("football.ankle_sprain", "g_hot_joint", "e_severe"),
    ("football.ankle_sprain", "g_dvt", "e_breath"),
    ("football.ankle_sprain", "g_trend", "c_rapid"),
    ("football.ankle_sprain", "g_medical", "c_postop_worse"),
    ("football.ankle_sprain", "a_location", "c_bone"),
    ("football.ankle_sprain", "a_walk", "c_cannot"),
    ("football.ankle_sprain", "a_midfoot", "c_present"),
    ("football.ankle_sprain", "a_instability", "c_gross"),
    ("football.ankle_sprain", "a_achilles", "c_present"),
    ("football.ankle_sprain", "g_rest_pain", "c_severe"),
    ("football.ankle_sprain", "g_comorbid", "p_present"),
    ("football.ankle_sprain", "g_help_access", "p_no_access"),
    ("football.ankle_sprain", "a_mechanism", "p_rotation"),
    ("football.finger_sprain", "f_deformity", "e_open_circ"),
    ("football.finger_sprain", "f_deformity", "c_present"),
    ("football.hamstring_strain", "h_nerve", "e_cauda"),
    ("football.hamstring_strain", "h_nerve", "c_weakness"),
    ("football.hamstring_strain", "h_nerve", "p_tingling"),
    ("football.quadriceps_strain", "qd_extension", "c_cannot"),
    ("basketball.quadriceps_strain", "qd_extension", "c_cannot"),
)

#: Вопросы, которые задаются только после положительного ответа на скринер.
GATED = ("g_deformity", "g_circulation", "g_pain_swelling", "g_hot_joint", "g_dvt")


@pytest.fixture(scope="module")
def prod() -> ScenarioRegistry:
    return load_registry(PROD_DEFS_DIR)


def risky_options(scenario: Scenario) -> dict[str, set[str]]:
    """Варианты, которые задевают red flag или правило «к специалисту»."""
    from core.scenarios.loader import condition_question_refs

    risky: dict[str, set[str]] = {}

    def add(key: str, options: list[str]) -> None:
        risky.setdefault(key, set()).update(options)

    for flag in scenario.red_flags:
        implicit = flag.when.get("equals") or flag.when.get("in")
        if isinstance(implicit, str):
            add(flag.question, [implicit])
        elif isinstance(implicit, list):
            add(flag.question, [str(v) for v in implicit])
        else:
            for key, options in condition_question_refs(flag.when):
                add(key, options)

    for rule in scenario.routing:
        if rule.outcome is Outcome.REFER_SPECIALIST and rule.when is not None:
            for key, options in condition_question_refs(rule.when):
                add(key, options)
    return risky


#: «Ничего особенного» в порядке предпочтения: просто первый незадетый вариант не
#: подходит, потому что у g_trend это `p_moderate` — стойкие умеренные симптомы.
BENIGN_PREFERENCE = (
    "none",
    "absent",
    "improving",
    "mild_decreasing",
    "sleep_ok",
    "walked",
    "accessible",
    "adult",
    "adult_involved",
    "inward",
    "soft_outside",
    "load_only",
    "agreed",
    "ready",
)


def benign_walk(engine: ScenarioEngine) -> tuple[TriageDecision, dict[str, str]]:
    """Проход «ни одного тревожного признака»: ответы не задевают правил к врачу."""
    risky = risky_options(engine.scenario)
    answers: dict[str, str] = {}
    while True:
        step = engine.step(answers)
        if isinstance(step, TriageDecision):
            return step, answers
        question = step.question
        dangerous = risky.get(question.key, set())
        safe = [o for o in question.option_ids() if o not in dangerous and o != "unknown"]
        preferred = next((o for o in BENIGN_PREFERENCE if o in safe), None)
        answers[question.key] = preferred or (safe[0] if safe else "unknown")


class TestTiers:
    def test_default_rule_leads_to_self_rehab(self, prod: ScenarioRegistry) -> None:
        """Иначе «всё остальное» снова означало бы направление к врачу."""
        for scenario in prod.scenarios.values():
            default = scenario.routing[-1]
            assert default.is_default, scenario.id
            assert default.outcome is Outcome.SELF_REHAB, scenario.id
            assert default.plan in scenario.plans, scenario.id

    def test_unknown_answers_no_longer_route_to_doctor_by_default(
        self, prod: ScenarioRegistry
    ) -> None:
        """Ответ «не знаю» сохраняет направление только там, где он опасен сам по себе."""
        kept = [
            rule.reason_code
            for scenario in prod.scenarios.values()
            for rule in scenario.routing
            if (rule.reason_code or "").startswith("unclear_")
            and rule.outcome is Outcome.REFER_SPECIALIST
        ]
        removed_suffixes = {"g_sleep", "g_history", "g_prior_eval", "g_program", "g_comorbid"}
        assert not [r for r in kept if r and r.removeprefix("unclear_") in removed_suffixes]


class TestSafetyFloor:
    @pytest.mark.parametrize(("scenario_id", "question_key", "option_id"), MUST_REFER)
    def test_single_danger_sign_still_refers(
        self, prod: ScenarioRegistry, scenario_id: str, question_key: str, option_id: str
    ) -> None:
        """Один тревожный ответ на спокойном фоне обязан перевесить весь остальной опрос."""
        scenario = prod.require(scenario_id)
        engine = ScenarioEngine(scenario)
        _, answers = benign_walk(engine)

        question = scenario.question(question_key)
        assert question is not None, f"{scenario_id}: нет вопроса {question_key}"
        assert option_id in question.option_ids(), f"{scenario_id}/{question_key}: {option_id}"

        answers[question_key] = option_id
        decision = engine.route(answers)
        assert decision.outcome is Outcome.REFER_SPECIALIST, (
            f"{scenario_id}: {question_key}={option_id} больше не ведёт к специалисту "
            f"(исход {decision.outcome.value}, причина {decision.reason_codes})"
        )

    def test_red_flags_untouched(self, prod: ScenarioRegistry) -> None:
        for scenario in prod.scenarios.values():
            for flag in scenario.red_flags:
                assert flag.outcome is Outcome.REFER_SPECIALIST, f"{scenario.id}/{flag.id}"


class TestReferralRate:
    def test_benign_user_gets_a_plan(self, prod: ScenarioRegistry) -> None:
        """Человек без тревожных признаков не должен уходить к врачу ни в одном сценарии."""
        referred = [
            scenario.id
            for scenario in prod.scenarios.values()
            if benign_walk(ScenarioEngine(scenario))[0].outcome is Outcome.REFER_SPECIALIST
        ]
        assert not referred, f"благополучный путь всё ещё ведёт к врачу: {referred}"

    def test_random_walk_referral_share_under_cap(self, prod: ScenarioRegistry) -> None:
        """Равномерный выбор завышает долю тревожных ответов, но не до 100%, как раньше."""
        rng = random.Random(20261023)
        self_rehab = 0
        total = 0
        for scenario in prod.scenarios.values():
            engine = ScenarioEngine(scenario)
            for _ in range(200):
                answers: dict[str, str] = {}
                while True:
                    step = engine.step(answers)
                    if isinstance(step, TriageDecision):
                        break
                    answers[step.question.key] = rng.choice(step.question.option_ids())
                total += 1
                if step.outcome is not Outcome.REFER_SPECIALIST:
                    self_rehab += 1
        assert self_rehab > 0, "ни один случайный проход не дошёл до плана"


class TestSurveyLength:
    def test_declared_question_count(self, prod: ScenarioRegistry) -> None:
        for scenario in prod.scenarios.values():
            assert len(scenario.questions) <= 26, scenario.id

    def test_benign_path_is_shorter_than_before(self, prod: ScenarioRegistry) -> None:
        """До правки благополучный путь занимал 21–23 вопроса."""
        for scenario in prod.scenarios.values():
            _, answers = benign_walk(ScenarioEngine(scenario))
            assert len(answers) <= 18, f"{scenario.id}: задано {len(answers)} вопросов"


class TestEmergencyScreener:
    def test_screener_exists_and_gates_the_cascade(self, prod: ScenarioRegistry) -> None:
        for scenario in prod.scenarios.values():
            if scenario.question("g_alarm") is None:
                continue
            keys = scenario.question_keys()
            assert keys.index("g_alarm") < min(keys.index(k) for k in GATED if k in keys), (
                f"{scenario.id}: скринер должен стоять до детальных вопросов"
            )
            for key in GATED:
                question = scenario.question(key)
                if question is not None:
                    assert question.ask_if is not None, f"{scenario.id}/{key}"

    def test_unknown_on_screener_still_opens_the_cascade(self, prod: ScenarioRegistry) -> None:
        """Иначе «не знаю» пропускал бы и вопросы, и привязанные к ним red flags."""
        scenario = prod.require("football.ankle_sprain")
        engine = ScenarioEngine(scenario)
        asked = {
            step.question.key
            for answers in [{"g_age": "adult", "g_trend": "improving", "g_alarm": "unknown"}]
            for step in [engine.step(answers)]
        }
        assert asked & set(GATED), "каскад не раскрылся на ответе «не знаю»"

    def test_none_on_screener_skips_the_cascade(self, prod: ScenarioRegistry) -> None:
        scenario = prod.require("football.ankle_sprain")
        engine = ScenarioEngine(scenario)
        _, answers = benign_walk(engine)
        assert answers.get("g_alarm") == "none"
        assert not set(GATED) & set(answers)


class TestPainMaps:
    def test_images_are_known(self, prod: ScenarioRegistry) -> None:
        for scenario in prod.scenarios.values():
            if scenario.pain_map is not None:
                assert scenario.pain_map.image in PAIN_POINT_IMAGES, scenario.id

    def test_region_matches_image(self, prod: ScenarioRegistry) -> None:
        for scenario in prod.scenarios.values():
            if scenario.pain_map is not None and scenario.body_region is not None:
                assert scenario.pain_map.image == scenario.body_region, scenario.id
