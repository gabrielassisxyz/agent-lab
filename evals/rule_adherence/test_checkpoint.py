"""Tests for per-cell durability and resume.

The behaviour under test is what the first full run did not have: a grid that can be
killed and picked up without losing what it already paid for, and without quietly
counting a failed call as a clean pass.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from .checkpoint import Checkpoint, cell_key
from .placements import Axes
from .runner import RunOutcome
from .schema import CheckOutcome, Usage


def _outcome(task="t1", placement="hybrid", rep=0, axes=None, passed=True,
             error=None, usage=None, trace=None):
    return RunOutcome(
        task_id=task, placement=placement, rep=rep, axes=axes or Axes(),
        outcome=None if error else CheckOutcome(passed=passed,
                                                failure_mode=None if passed else "ignored"),
        usage=usage or Usage(), error=error, trace=trace or {},
    )


class CheckpointCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.cp = Checkpoint(self.dir)

    def tearDown(self):
        self._tmp.cleanup()


class TestRecording(CheckpointCase):
    def test_a_missing_checkpoint_is_empty_not_an_error(self):
        self.assertEqual(self.cp.completed(), set())
        self.assertEqual(self.cp.outcomes(), [])

    def test_a_recorded_cell_counts_as_done(self):
        self.cp.record(_outcome())
        self.assertIn(cell_key("t1", "hybrid", Axes(), 0), self.cp.completed())

    def test_each_cell_is_written_immediately(self):
        self.cp.record(_outcome(task="a"))
        self.assertTrue(self.cp.cells_path.exists())
        self.cp.record(_outcome(task="b"))
        self.assertEqual(len(self.cp.cells_path.read_text().strip().splitlines()), 2)

    def test_axes_are_part_of_a_cell_identity(self):
        # Widening the grid later must not collide with results recorded under a
        # narrower one, or a resume would skip cells it never ran.
        self.cp.record(_outcome(axes=Axes(turns=1)))
        self.assertNotIn(cell_key("t1", "hybrid", Axes(turns=20), 0), self.cp.completed())

    def test_the_trace_is_persisted_for_later_reading(self):
        self.cp.record(_outcome(trace={"turns": ["hello"], "events": []}))
        written = list(self.cp.traces_dir.glob("*.json"))
        self.assertEqual(len(written), 1)
        self.assertEqual(json.loads(written[0].read_text())["turns"], ["hello"])


class TestResume(CheckpointCase):
    def test_an_errored_cell_is_not_counted_as_done(self):
        self.cp.record(_outcome(error="exit 1 on turn 0"))
        self.assertEqual(self.cp.completed(), set())

    def test_a_retried_cell_supersedes_its_error(self):
        self.cp.record(_outcome(error="rate limited"))
        self.cp.record(_outcome(passed=True))
        self.assertIn(cell_key("t1", "hybrid", Axes(), 0), self.cp.completed())
        outcomes = self.cp.outcomes()
        self.assertEqual(len(outcomes), 1)
        self.assertIsNone(outcomes[0].error)
        self.assertTrue(outcomes[0].outcome.passed)

    def test_outcomes_round_trip_through_disk(self):
        self.cp.record(_outcome(passed=False, axes=Axes(turns=5, filler_tokens=800),
                                usage=Usage(input_tokens=120, output_tokens=30)))
        restored = self.cp.outcomes()[0]
        self.assertFalse(restored.outcome.passed)
        self.assertEqual(restored.outcome.failure_mode, "ignored")
        self.assertEqual(restored.axes.turns, 5)
        self.assertEqual(restored.axes.filler_tokens, 800)
        self.assertEqual(restored.usage.input_tokens, 120)

    def test_a_line_torn_by_a_kill_is_skipped_not_fatal(self):
        self.cp.record(_outcome(task="good"))
        with self.cp.cells_path.open("a") as handle:
            handle.write('{"key": "half-writ')
        self.assertEqual(len(self.cp.outcomes()), 1)
        self.assertEqual(self.cp.outcomes()[0].task_id, "good")


if __name__ == "__main__":
    unittest.main()
