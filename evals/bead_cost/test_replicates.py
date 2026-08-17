"""The replicate machinery, at the two places where being wrong would be invisible.

A draw that quietly reuses a run makes one sample count twice and replication stops being
replication. A statistic implemented by hand agrees with a table or it does not, and a p-value that
is merely plausible is worse than none - it would be quoted.
"""

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aggregate_replicates import arm_of, chi2_sf, friedman, ranks_with_ties  # noqa: E402
from build_replicates import usable_runs  # noqa: E402


class ChiSquare(unittest.TestCase):
    """Against printed table values, because that is the only check that is not self-referential."""

    TABLE = [(3.841, 1, 0.05), (5.991, 2, 0.05), (7.815, 3, 0.05), (9.488, 4, 0.05),
             (11.070, 5, 0.05), (6.635, 1, 0.01), (13.277, 4, 0.01), (20.515, 8, 0.0085)]

    def test_matches_the_table(self):
        for x, df, want in self.TABLE:
            self.assertAlmostEqual(want, chi2_sf(x, df), delta=0.0015, msg=f"chi2({x}, {df})")

    def test_zero_is_certain_and_large_is_vanishing(self):
        self.assertEqual(1.0, chi2_sf(0.0, 4))
        self.assertLess(chi2_sf(100.0, 4), 1e-15)


class Ranking(unittest.TestCase):
    def test_ties_share_the_average_rank(self):
        # Without this, two arms on the same mean rank get ordered by dictionary key and the report
        # states a preference no reviewer expressed.
        self.assertEqual({"a": 1.0, "b": 2.5, "c": 2.5, "d": 4.0},
                         ranks_with_ties({"a": 1.0, "b": 2.0, "c": 2.0, "d": 9.0}))

    def test_a_block_with_no_ties_is_ordinary(self):
        self.assertEqual({"a": 1.0, "b": 2.0, "c": 3.0},
                         ranks_with_ties({"a": 0.5, "b": 1.5, "c": 2.5}))


class Friedman(unittest.TestCase):
    def test_perfect_agreement_is_w_of_one(self):
        blocks = [{"a": 1, "b": 2, "c": 3, "d": 4} for _ in range(5)]
        _, _, p, w = friedman(blocks)
        self.assertAlmostEqual(1.0, w, places=6)
        self.assertLess(p, 0.01)

    def test_orderings_that_cancel_out_are_w_of_zero(self):
        blocks = [{"a": 1, "b": 2, "c": 3, "d": 4}, {"a": 4, "b": 3, "c": 2, "d": 1},
                  {"a": 2, "b": 1, "c": 4, "d": 3}, {"a": 3, "b": 4, "c": 1, "d": 2}]
        chi, _, p, w = friedman(blocks)
        self.assertAlmostEqual(0.0, w, places=6)
        self.assertAlmostEqual(0.0, chi, places=6)
        self.assertGreater(p, 0.99)

    def test_the_panel_this_run_produced(self):
        # The four reviewers of the first real packet, as ranks. Recorded so a change to the
        # statistic shows up against a case whose numbers were computed by hand.
        blocks = [{"B": 2, "D": 1, "A": 3, "C": 4, "E": 5},
                  {"B": 1, "D": 2, "A": 3, "C": 4, "E": 5},
                  {"B": 1, "D": 4, "A": 2, "C": 5, "E": 3},
                  {"B": 2, "D": 1, "A": 3, "C": 4, "E": 5}]
        chi, df, p, w = friedman(blocks)
        self.assertEqual(4, df)
        self.assertAlmostEqual(11.4, chi, delta=0.05)
        self.assertAlmostEqual(0.71, w, delta=0.01)
        self.assertAlmostEqual(0.022, p, delta=0.002)


class ArmOf(unittest.TestCase):
    def test_a_run_entry_becomes_its_arm(self):
        self.assertEqual("deepseek-pro-high", arm_of("deepseek-pro-high / llmux-dshigh-03"))

    def test_the_reference_is_its_own_treatment(self):
        self.assertEqual("reference commit 3d6a5a2", arm_of("reference commit 3d6a5a2"))


class UsableRuns(unittest.TestCase):
    """Derived from the verdicts, because a hardcoded list of good runs rots on the next campaign."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.root = pathlib.Path(self._dir.name)

    def write(self, name: str, verdict: dict | None):
        directory = self.root / name
        directory.mkdir()
        if verdict is not None:
            (directory / "verdict.json").write_text(json.dumps(verdict))

    def test_keeps_only_scored_building_fully_passing_runs(self):
        self.write("llmux-x-01", {"scored": True, "build_failed": True, "passed": 0, "total": 16})
        self.write("llmux-x-02", {"scored": True, "build_failed": False, "passed": 16, "total": 16})
        self.write("llmux-x-03", {"scored": True, "build_failed": False, "passed": 15, "total": 16})
        self.write("llmux-x-04", None)                       # a launch that never became a run
        self.write("llmux-x-05", {"scored": True, "build_failed": False, "passed": 16, "total": 16})
        self.assertEqual(["llmux-x-02", "llmux-x-05"], usable_runs(self.root, "llmux-x"))

    def test_a_longer_prefix_is_not_swallowed_by_a_shorter_one(self):
        # `llmux-ds` and `llmux-dshigh` are both real prefixes in this campaign, and a glob that
        # matched loosely would put one arm's runs inside another's pool.
        self.write("llmux-ds-01", {"scored": True, "build_failed": False, "passed": 16, "total": 16})
        self.write("llmux-dshigh-01",
                   {"scored": True, "build_failed": False, "passed": 16, "total": 16})
        self.assertEqual(["llmux-ds-01"], usable_runs(self.root, "llmux-ds"))


if __name__ == "__main__":
    unittest.main()
