from __future__ import annotations

import random

import pytest

from core.domain.enums import Outcome
from core.scenarios.engine import (
    AskQuestion,
    ScenarioEngine,
    TriageDecision,
    evaluate_condition,
)


class TestConditions:
    def test_question_equals(self) -> None:
        assert evaluate_condition({"q_swelling": "severe"}, {"q_swelling": "severe"})
        assert not evaluate_condition({"q_swelling": "severe"}, {"q_swelling": "none"})

    def test_question_in_list(self) -> None:
        cond = {"q_swelling": ["none", "moderate"]}
        assert evaluate_condition(cond, {"q_swelling": "moderate"})
        assert not evaluate_condition(cond, {"q_swelling": "severe"})

    def test_unanswered_is_false(self) -> None:
        assert not evaluate_condition({"q_swelling": "none"}, {})

    def test_all_any_not(self) -> None:
        answers = {"a": "1", "b": "2"}
        assert evaluate_condition({"all": [{"a": "1"}, {"b": "2"}]}, answers)
        assert not evaluate_condition({"all": [{"a": "1"}, {"b": "9"}]}, answers)
        assert evaluate_condition({"any": [{"a": "9"}, {"b": "2"}]}, answers)
        assert evaluate_condition({"not": {"a": "9"}}, answers)

    def test_implicit_subject(self) -> None:
        assert evaluate_condition({"equals": "cannot"}, {}, subject="cannot")
        assert not evaluate_condition({"equals": "cannot"}, {}, subject="freely")
        assert evaluate_condition({"in": ["cannot", "with_pain"]}, {}, subject="with_pain")


class TestQuestionFlow:
    def test_asks_questions_in_order(self, ankle_engine: ScenarioEngine) -> None:
        answers: dict[str, str] = {}
        asked = []
        for _ in range(10):
            step = ankle_engine.step(answers)
            if not isinstance(step, AskQuestion):
                break
            asked.append(step.question.key)
            # отвечаем первым «безопасным» вариантом
            safe = {
                "q_when": "today",
                "q_weightbearing": "with_pain",
                "q_deformity": "absent",
                "q_swelling": "moderate",
                "q_history": "first_time",
            }
            answers[step.question.key] = safe[step.question.key]
        assert asked == list(ankle_engine.scenario.question_keys())

    def test_progress_counts_applicable(self, ankle_engine: ScenarioEngine) -> None:
        answered, total = ankle_engine.progress({"q_when": "today"})
        assert (answered, total) == (1, 5)

    def test_next_question_none_when_complete(self, ankle_engine: ScenarioEngine) -> None:
        answers = {
            "q_when": "today",
            "q_weightbearing": "with_pain",
            "q_deformity": "absent",
            "q_swelling": "moderate",
            "q_history": "first_time",
        }
        assert ankle_engine.next_question(answers) is None


class TestRedFlags:
    def test_cannot_bear_weight_stops_survey(self, ankle_engine: ScenarioEngine) -> None:
        answers = {"q_when": "today", "q_weightbearing": "cannot"}
        step = ankle_engine.step(answers)
        assert isinstance(step, TriageDecision)
        assert step.outcome is Outcome.REFER_SPECIALIST
        assert step.triggered_flags == ("rf_weightbearing",)

    def test_deformity_stops_survey(self, ankle_engine: ScenarioEngine) -> None:
        step = ankle_engine.step({"q_deformity": "present"})
        assert isinstance(step, TriageDecision)
        assert step.triggered_flags == ("rf_deformity",)

    def test_no_flag_when_answers_safe(self, ankle_engine: ScenarioEngine) -> None:
        assert ankle_engine.check_red_flags({"q_weightbearing": "with_pain"}) is None

    def test_knee_locking_is_flag(self, knee_engine: ScenarioEngine) -> None:
        step = knee_engine.step({"q_locking": "present"})
        assert isinstance(step, TriageDecision)
        assert step.triggered_flags == ("rf_locking",)

    def test_red_flag_beats_routing(self, ankle_engine: ScenarioEngine) -> None:
        """Полный набор ответов «на план», но красный флаг перевешивает."""
        answers = {
            "q_when": "today",
            "q_weightbearing": "cannot",
            "q_deformity": "absent",
            "q_swelling": "none",
            "q_history": "first_time",
        }
        decision = ankle_engine.route(answers)
        assert decision.outcome is Outcome.REFER_SPECIALIST
        assert decision.plan_key is None


class TestRouting:
    def test_mild_sprain_gets_plan(self, ankle_engine: ScenarioEngine) -> None:
        answers = {
            "q_when": "today",
            "q_weightbearing": "with_pain",
            "q_deformity": "absent",
            "q_swelling": "moderate",
            "q_history": "first_time",
        }
        decision = ankle_engine.route(answers)
        assert decision.outcome is Outcome.RECOVERY_PLAN
        assert decision.plan_key == "ankle_sprain_basic"
        assert decision.reason_codes == ("mild_sprain",)

    def test_severe_swelling_falls_to_default(self, ankle_engine: ScenarioEngine) -> None:
        answers = {
            "q_when": "today",
            "q_weightbearing": "freely",
            "q_deformity": "absent",
            "q_swelling": "severe",
            "q_history": "first_time",
        }
        decision = ankle_engine.route(answers)
        assert decision.outcome is Outcome.REFER_SPECIALIST
        assert decision.reason_codes == ("default_referral",)

    def test_old_injury_with_swelling_referred(self, ankle_engine: ScenarioEngine) -> None:
        answers = {
            "q_when": "more_week",
            "q_weightbearing": "with_pain",
            "q_deformity": "absent",
            "q_swelling": "moderate",
            "q_history": "repeat",
        }
        decision = ankle_engine.route(answers)
        assert decision.reason_codes == ("persistent_swelling",)

    def test_knee_overload_gets_plan(self, knee_engine: ScenarioEngine) -> None:
        answers = {
            "q_onset": "gradual",
            "q_duration": "weeks_2_6",
            "q_location": "below_kneecap",
            "q_locking": "absent",
            "q_giving_way": "absent",
            "q_swelling": "none",
            "q_pain_timing": "during_load",
        }
        decision = knee_engine.route(answers)
        assert decision.outcome is Outcome.RECOVERY_PLAN
        assert decision.plan_key == "patellar_load_management"

    def test_knee_chronic_referred(self, knee_engine: ScenarioEngine) -> None:
        answers = {
            "q_onset": "gradual",
            "q_duration": "weeks_6_plus",
            "q_location": "below_kneecap",
            "q_locking": "absent",
            "q_giving_way": "absent",
            "q_swelling": "none",
            "q_pain_timing": "after_load",
        }
        decision = knee_engine.route(answers)
        assert decision.outcome is Outcome.REFER_SPECIALIST
        assert decision.reason_codes == ("chronic_pain",)


class TestDeterminism:
    @pytest.mark.parametrize("repeat", range(3))
    def test_same_answers_same_outcome(self, knee_engine: ScenarioEngine, repeat: int) -> None:
        answers = {
            "q_onset": "gradual",
            "q_duration": "weeks_0_2",
            "q_location": "around_kneecap",
            "q_locking": "absent",
            "q_giving_way": "absent",
            "q_swelling": "moderate",
            "q_pain_timing": "after_load",
        }
        assert knee_engine.route(answers) == knee_engine.route(dict(answers))

    def test_every_answer_combination_routes(self, ankle_engine: ScenarioEngine) -> None:
        """Ни одна комбинация ответов не остаётся без исхода.

        Полный перебор невозможен: у сценария 24 вопроса, ~1e14 комбинаций.
        Берём детерминированную выборку — крайние точки (все первые / все последние
        варианты, каждый вариант поодиночке на фоне первых) плюс псевдослучайные
        комбинации с фиксированным seed.
        """
        questions = ankle_engine.scenario.questions
        keys = [q.key for q in questions]
        options = [tuple(q.option_ids()) for q in questions]

        combos: list[tuple[str, ...]] = [
            tuple(opts[0] for opts in options),
            tuple(opts[-1] for opts in options),
        ]
        # каждый вариант каждого вопроса хотя бы раз, остальные ответы — первый вариант
        baseline = combos[0]
        for index, opts in enumerate(options):
            for option_id in opts:
                combos.append((*baseline[:index], option_id, *baseline[index + 1 :]))
        rnd = random.Random(20240501)
        combos.extend(tuple(rnd.choice(opts) for opts in options) for _ in range(2000))

        for combo in combos:
            answers = dict(zip(keys, combo, strict=True))
            decision = ankle_engine.route(answers)
            assert decision.outcome in (Outcome.REFER_SPECIALIST, Outcome.RECOVERY_PLAN)
            if decision.outcome is Outcome.RECOVERY_PLAN:
                assert decision.plan_key in ankle_engine.scenario.plans
