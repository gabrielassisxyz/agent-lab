"""Tests for the task admission test.

This is the guard against the failure that made the first full run meaningless: a
task-set whose members pass whether or not the rule is present. The verdicts have to
be sharp, because "admissible" is what entitles a task's cells to be counted in a
placement comparison.
"""

from __future__ import annotations

import unittest

from .placements import CONTROL
from .runner import RunOutcome
from .schema import CheckOutcome
from .screening import ADMISSIBLE, MEASURES_PRIOR, UNREACHABLE, admissible_ids, screen


def _run(task, placement, passed, error=None):
    return RunOutcome(
        task_id=task, placement=placement,
        outcome=None if error else CheckOutcome(passed=passed,
                                                failure_mode=None if passed else "ignored"),
        error=error,
    )


def _verdict(outcomes, task):
    return next(s.verdict for s in screen(outcomes) if s.task_id == task)


class TestVerdicts(unittest.TestCase):
    def test_a_task_the_model_always_passes_without_rules_measures_the_prior(self):
        outcomes = [
            _run("t", CONTROL, True),
            _run("t", "hybrid", True),
        ]
        self.assertEqual(_verdict(outcomes, "t"), MEASURES_PRIOR)

    def test_partial_headroom_is_admissible_not_disqualifying(self):
        # The strict reading ("the control must never pass") throws away exactly the
        # middle of the range, which for a stochastic agent is where the measurable
        # tasks live. This lab already settled that with a band rather than a point.
        outcomes = [
            _run("t", CONTROL, False), _run("t", CONTROL, False), _run("t", CONTROL, True),
            _run("t", "hybrid", True), _run("t", "hybrid", True), _run("t", "hybrid", True),
        ]
        self.assertEqual(_verdict(outcomes, "t"), ADMISSIBLE)

    def test_failing_the_control_and_passing_an_arm_is_admissible(self):
        outcomes = [
            _run("t", CONTROL, False),
            _run("t", "jit-near-query", True),
            _run("t", "front-load-all", False),
        ]
        self.assertEqual(_verdict(outcomes, "t"), ADMISSIBLE)

    def test_a_control_above_the_ceiling_is_out(self):
        outcomes = [
            _run("t", CONTROL, True), _run("t", CONTROL, True), _run("t", CONTROL, True),
            _run("t", "hybrid", True),
        ]
        self.assertEqual(_verdict(outcomes, "t"), MEASURES_PRIOR)

    def test_failing_every_arm_means_prose_cannot_reach_it(self):
        outcomes = [
            _run("t", CONTROL, False),
            _run("t", "hybrid", False),
            _run("t", "jit-near-query", False),
        ]
        self.assertEqual(_verdict(outcomes, "t"), UNREACHABLE)

    def test_an_arm_below_the_floor_is_unreachable(self):
        outcomes = [
            _run("t", CONTROL, False), _run("t", CONTROL, False), _run("t", CONTROL, False),
            _run("t", "hybrid", False), _run("t", "hybrid", False), _run("t", "hybrid", False),
            _run("t", "jit-near-query", False), _run("t", "jit-near-query", False),
            _run("t", "jit-near-query", False), _run("t", "jit-near-query", True),
        ]
        self.assertEqual(_verdict(outcomes, "t"), UNREACHABLE)

    def test_effect_is_measured_against_the_control(self):
        # An arm at 0.9 means nothing until you know the control was at 0.85.
        outcomes = [
            _run("t", CONTROL, False), _run("t", CONTROL, True),
            _run("t", "hybrid", True), _run("t", "hybrid", True),
        ]
        found = screen(outcomes)[0]
        self.assertAlmostEqual(found.effect, 0.5)

    def test_a_sweep_without_a_control_arm_says_so(self):
        self.assertEqual(_verdict([_run("t", "hybrid", True)], "t"), "not-screened")


class TestDetails(unittest.TestCase):
    def test_the_best_arm_is_reported(self):
        outcomes = [
            _run("t", CONTROL, False),
            _run("t", "hybrid", False), _run("t", "hybrid", False),
            _run("t", "jit-near-query", True), _run("t", "jit-near-query", True),
        ]
        found = screen(outcomes)[0]
        self.assertEqual(found.best_arm, "jit-near-query")
        self.assertEqual(found.best_arm_pass_rate, 1.0)

    def test_errored_cells_are_excluded_before_judging(self):
        # A cell that failed to run is not a cell that failed.
        outcomes = [
            _run("t", CONTROL, False, error="rate limited"),
            _run("t", CONTROL, False),
            _run("t", "hybrid", True),
        ]
        found = screen(outcomes)[0]
        self.assertEqual(found.control_n, 1)
        self.assertEqual(found.verdict, ADMISSIBLE)

    def test_admissible_ids_filters(self):
        outcomes = [
            _run("keep", CONTROL, False), _run("keep", "hybrid", True),
            _run("drop", CONTROL, True), _run("drop", "hybrid", True),
        ]
        self.assertEqual(admissible_ids(screen(outcomes)), ["keep"])


if __name__ == "__main__":
    unittest.main()
