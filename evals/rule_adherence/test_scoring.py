"""Tests for the paired comparison.

The design is paired: every arm runs every task. Analysing it as unpaired throws that
away and reports the task-difficulty spread as if it were noise, which is the weakest
reading of the data available. These tests pin the arithmetic and the guards.
"""

from __future__ import annotations

import unittest

from .placements import CONTROL
from .runner import RunOutcome
from .schema import CheckOutcome
from .scoring import arm_effects, score, task_effects


def _cells(task: str, placement: str, passes: int, total: int) -> list[RunOutcome]:
    return [
        RunOutcome(task_id=task, placement=placement,
                   outcome=CheckOutcome(passed=index < passes,
                                        failure_mode=None if index < passes else "ignored"))
        for index in range(total)
    ]


# The worked example: six tasks spanning the difficulty range, an arm that adds one
# pass to five of them. Kept as a regression because it is the case that shows what
# pairing buys.
WORKED_EXAMPLE: list[RunOutcome] = []
for _task, _control_passes, _arm_passes in [
    ("a", 0, 1), ("b", 1, 2), ("c", 2, 3), ("d", 0, 1), ("e", 1, 2), ("f", 3, 3),
]:
    WORKED_EXAMPLE += _cells(_task, CONTROL, _control_passes, 3)
    WORKED_EXAMPLE += _cells(_task, "hybrid", _arm_passes, 3)


class TestWorkedExample(unittest.TestCase):
    def test_the_pooled_rates_are_what_they_look_like(self):
        by = {s.placement: s for s in score(WORKED_EXAMPLE)}
        self.assertAlmostEqual(by[CONTROL].pass_rate, 7 / 18)
        self.assertAlmostEqual(by["hybrid"].pass_rate, 12 / 18)

    def test_pairing_finds_the_same_mean_effect(self):
        arm = arm_effects(WORKED_EXAMPLE)[0]
        self.assertAlmostEqual(arm.mean_effect, 12 / 18 - 7 / 18)

    def test_pairing_is_far_more_sensitive_than_pooling(self):
        # Pooled, this reads as roughly 1.7 standard errors and convinces nobody.
        # Paired, the task-difficulty spread cancels and the same data reads as 5.0.
        arm = arm_effects(WORKED_EXAMPLE)[0]
        self.assertAlmostEqual(arm.standard_errors, 5.0)

    def test_it_reports_how_many_tasks_moved(self):
        arm = arm_effects(WORKED_EXAMPLE)[0]
        self.assertEqual((arm.improved, arm.unchanged, arm.regressed), (5, 1, 0))


class TestTaskEffects(unittest.TestCase):
    def test_an_effect_is_the_arm_minus_the_control_on_that_task(self):
        outcomes = _cells("t", CONTROL, 1, 3) + _cells("t", "hybrid", 3, 3)
        found = task_effects(outcomes)[0]
        self.assertAlmostEqual(found.control_rate, 1 / 3)
        self.assertAlmostEqual(found.arm_rate, 1.0)
        self.assertAlmostEqual(found.effect, 2 / 3)

    def test_a_task_without_a_control_is_skipped_not_compared_against_zero(self):
        outcomes = _cells("t", "hybrid", 3, 3)
        self.assertEqual(task_effects(outcomes), [])

    def test_the_control_is_not_compared_against_itself(self):
        outcomes = _cells("t", CONTROL, 1, 3) + _cells("t", "hybrid", 2, 3)
        self.assertEqual({e.placement for e in task_effects(outcomes)}, {"hybrid"})

    def test_errored_cells_do_not_count_as_failures(self):
        outcomes = _cells("t", CONTROL, 0, 3) + _cells("t", "hybrid", 2, 2)
        outcomes.append(RunOutcome(task_id="t", placement="hybrid", error="rate limited"))
        found = task_effects(outcomes)[0]
        self.assertEqual(found.n_arm, 2)
        self.assertAlmostEqual(found.arm_rate, 1.0)

    def test_a_regression_is_reported_as_negative(self):
        outcomes = _cells("t", CONTROL, 3, 3) + _cells("t", "front-load-all", 0, 3)
        self.assertAlmostEqual(task_effects(outcomes)[0].effect, -1.0)


class TestArmEffects(unittest.TestCase):
    def test_only_the_named_tasks_are_compared(self):
        # In practice this is the set the screening admitted. Averaging real effects
        # with the structural zeros of tasks the model passes unprompted would report
        # a genuine effect as a smaller one.
        outcomes = (_cells("keep", CONTROL, 0, 3) + _cells("keep", "hybrid", 3, 3)
                    + _cells("drop", CONTROL, 3, 3) + _cells("drop", "hybrid", 3, 3))
        both = arm_effects(outcomes)[0]
        admitted = arm_effects(outcomes, task_ids=["keep"])[0]
        self.assertAlmostEqual(both.mean_effect, 0.5)
        self.assertAlmostEqual(admitted.mean_effect, 1.0)
        self.assertEqual(admitted.tasks, 1)

    def test_a_single_task_has_no_spread_and_so_no_ratio(self):
        # Zero standard error is a small-sample artifact, not infinite confidence.
        outcomes = _cells("t", CONTROL, 0, 3) + _cells("t", "hybrid", 3, 3)
        arm = arm_effects(outcomes)[0]
        self.assertEqual(arm.standard_error, 0.0)
        self.assertIsNone(arm.standard_errors)

    def test_identical_effects_across_tasks_also_leave_no_ratio(self):
        outcomes = (_cells("a", CONTROL, 0, 3) + _cells("a", "hybrid", 3, 3)
                    + _cells("b", CONTROL, 0, 3) + _cells("b", "hybrid", 3, 3))
        arm = arm_effects(outcomes)[0]
        self.assertAlmostEqual(arm.mean_effect, 1.0)
        self.assertIsNone(arm.standard_errors)

    def test_no_admissible_tasks_yields_no_rows(self):
        outcomes = _cells("t", CONTROL, 3, 3) + _cells("t", "hybrid", 3, 3)
        self.assertEqual(arm_effects(outcomes, task_ids=[]), [])

    def test_every_arm_gets_its_own_row(self):
        outcomes = (_cells("t", CONTROL, 0, 3)
                    + _cells("t", "hybrid", 3, 3)
                    + _cells("t", "jit-near-query", 1, 3))
        self.assertEqual({a.placement for a in arm_effects(outcomes)},
                         {"hybrid", "jit-near-query"})


if __name__ == "__main__":
    unittest.main()
