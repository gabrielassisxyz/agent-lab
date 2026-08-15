"""Unit tests for the outcome vocabulary, built on synthetic run directories.

The classifier decides what goes in the denominator of a cost per completed bead, so every case it
collapses is a lane charged for something it did not do. The cases that matter are the ones that
look alike on disk: an unfinished edit left by a model and an unfinished edit left by a harness that
died are the same tree, and only the missing verdict beside a reported error tells them apart.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from classify import classify  # noqa: E402


def _run(tmp: pathlib.Path, *, verdict=None, record=None, stderr: str = "") -> pathlib.Path:
    run_dir = tmp / "run"
    run_dir.mkdir()
    if verdict is not None:
        (run_dir / "verdict.json").write_text(json.dumps(verdict))
    if record is not None:
        (run_dir / "record.json").write_text(json.dumps(record))
    if stderr:
        (run_dir / "stderr.txt").write_text(stderr)
    return run_dir


ALL_PASS = {"scored": True, "section_a": {f"a{n}": True for n in range(1, 6)}}
PARTIAL = {"scored": True, "section_a": {"a1": True, "a2": False, "a3": True, "a4": False, "a5": False}}
UNSCORED = {"scored": False, "reason": "no verdict line - the tree did not build or the test did not run"}

DIRTY = {"worktree": {"committed": False, "dirty": True, "diff_files": 4}}
COMMITTED = {"worktree": {"committed": True, "dirty": False, "diff_files": 4}}
CLEAN = {"worktree": {"committed": False, "dirty": False, "diff_files": 0}}


class ClassifyTest(unittest.TestCase):
    def outcome(self, **kwargs) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            return classify(_run(pathlib.Path(tmp), **kwargs))

    def test_every_criterion_passing_is_admitted(self):
        self.assertEqual(self.outcome(verdict=ALL_PASS, record=COMMITTED), "admitted")

    def test_a_graded_and_rejected_diff_is_wrong(self):
        self.assertEqual(self.outcome(verdict=PARTIAL, record=COMMITTED), "wrong")

    def test_a_finished_run_that_left_the_base_tree_is_no_diff(self):
        self.assertEqual(self.outcome(verdict=PARTIAL, record=CLEAN), "no-diff")

    def test_an_unscored_tree_left_by_a_dead_lane_is_aborted(self):
        record = dict(DIRTY, usage={"status": "ERROR"})
        self.assertEqual(self.outcome(verdict=UNSCORED, record=record), "aborted")

    def test_the_same_unscored_tree_without_a_lane_error_is_still_wrong(self):
        """The error is the whole discriminator - without it the model owns the unfinished edit."""
        self.assertEqual(self.outcome(verdict=UNSCORED, record=DIRTY), "wrong")

    def test_a_lane_error_after_a_graded_diff_does_not_excuse_the_diff(self):
        record = dict(COMMITTED, usage={"status": "ERROR"})
        self.assertEqual(self.outcome(verdict=PARTIAL, record=record), "wrong")

    def test_a_rate_limit_with_nothing_produced_is_unreachable(self):
        self.assertEqual(self.outcome(record=CLEAN, stderr="429 Too Many Requests"), "unreachable")

    def test_a_rate_limit_survived_by_a_run_that_produced_a_fix_is_admitted(self):
        """The regression that cost a lane a rest round: reachability read before what was produced."""
        outcome = self.outcome(verdict=ALL_PASS, record=COMMITTED, stderr="429 Too Many Requests")
        self.assertEqual(outcome, "admitted")

    def test_a_run_with_no_artefacts_at_all_is_broken(self):
        self.assertEqual(self.outcome(), "broken")


if __name__ == "__main__":
    unittest.main()
