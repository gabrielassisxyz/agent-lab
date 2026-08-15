"""The distinction the scorer exists to preserve: a tree that did not build is not a tree that
failed sixteen criteria. Both produce a non-zero `go test`, and pricing one as the other would
report a broken attempt as a wrong answer."""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from go_verdict import read_results, verdict  # noqa: E402


def event(test: str, action: str) -> str:
    return f'{{"Action":"{action}","Package":"p","Test":"{test}"}}'


class ReadResults(unittest.TestCase):
    def test_keeps_only_terminal_actions(self):
        lines = [event("TestA", "run"), event("TestA", "output"), event("TestA", "pass")]
        self.assertEqual({"TestA": "pass"}, read_results(lines))

    def test_ignores_non_json_build_errors(self):
        lines = ["# github.com/x/y", "./f.go:3:2: undefined: Reserve", event("TestA", "fail")]
        self.assertEqual({"TestA": "fail"}, read_results(lines))

    def test_ignores_package_level_events_without_a_test(self):
        lines = ['{"Action":"fail","Package":"p"}', event("TestA", "pass")]
        self.assertEqual({"TestA": "pass"}, read_results(lines))


class Verdict(unittest.TestCase):
    def test_a_tree_that_did_not_build_scores_every_criterion_false(self):
        # Not an unscored run: this bead's base tree does not compile, so a build failure is the
        # ordinary starting state and the ordinary shape of a solution that named things its own
        # way. Dropping those from the denominator would remove the hardest cases from the result.
        result = verdict("r", {}, ["TestA", "TestB"])
        self.assertTrue(result["scored"])
        self.assertTrue(result["build_failed"])
        self.assertEqual({"TestA": False, "TestB": False}, result["section_a"])
        self.assertEqual(0, result["passed"])

    def test_a_test_that_vanished_from_the_report_is_false_not_absent(self):
        result = verdict("r", {"TestA": "pass"}, ["TestA", "TestB"])
        self.assertEqual({"TestA": True, "TestB": False}, result["section_a"])
        self.assertEqual(2, result["total"])

    def test_unrunnable_suite_with_nothing_expected_is_unscored(self):
        result = verdict("r", {}, [])
        self.assertFalse(result["scored"])

    def test_partial_credit_is_reported_per_test(self):
        result = verdict("r", {"TestA": "pass", "TestB": "fail", "TestC": "pass"})
        self.assertTrue(result["scored"])
        self.assertEqual({"TestA": True, "TestB": False, "TestC": True}, result["section_a"])
        self.assertEqual(2, result["passed"])
        self.assertEqual(3, result["total"])

    def test_a_skipped_test_does_not_count_as_passed(self):
        # A run that makes the suite compile by skipping every assertion would otherwise score full
        # marks, which is the cheapest way to defeat this instrument.
        result = verdict("r", {"TestA": "skip"})
        self.assertEqual({"TestA": False}, result["section_a"])
        self.assertEqual(0, result["passed"])


if __name__ == "__main__":
    unittest.main()
