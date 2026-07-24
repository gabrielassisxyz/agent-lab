"""Tests for the distance filler.

The inertness tests are the point. Filler is injected into cells whose checkers read
the agent's commands and commit text, so padding that happened to contain a git verb
would be logged by the shim and charged to the agent, turning every safety cell into
a false violation. That failure would be invisible in the results: a uniformly worse
score across all arms reads as a hard task, not as a broken instrument.
"""

from __future__ import annotations

import unittest

from .checkers import no_destructive_git, no_assistant_attribution
from .context import assert_inert, estimate_tokens, filler_text, filler_turns
from .schema import AgentResult


class TestFillerText(unittest.TestCase):
    def test_empty_when_no_padding_is_asked_for(self):
        self.assertEqual(filler_text(0), "")
        self.assertEqual(filler_text(-5), "")

    def test_reaches_roughly_the_requested_size(self):
        text = filler_text(2000)
        self.assertGreaterEqual(estimate_tokens(text), 2000)
        self.assertLess(estimate_tokens(text), 2200)

    def test_is_deterministic_in_its_seed(self):
        self.assertEqual(filler_text(500, seed=7), filler_text(500, seed=7))

    def test_different_seeds_give_different_text(self):
        self.assertNotEqual(filler_text(500, seed=1), filler_text(500, seed=2))


class TestInertness(unittest.TestCase):
    def test_filler_never_looks_like_a_destructive_command(self):
        for seed in range(20):
            assert_inert(filler_text(1500, seed=seed))

    def test_filler_would_not_fail_the_safety_checker(self):
        text = filler_text(3000, seed=3)
        self.assertTrue(no_destructive_git(AgentResult(commands=[text])).passed)

    def test_filler_would_not_fail_the_attribution_checker(self):
        text = filler_text(3000, seed=4)
        self.assertTrue(no_assistant_attribution(AgentResult(commit_messages=[text])).passed)

    def test_turns_are_inert_too(self):
        for turn in filler_turns(12, seed=5):
            assert_inert(turn)

    def test_assert_inert_actually_catches_something(self):
        # A guard that cannot fail is not a guard.
        with self.assertRaises(ValueError):
            assert_inert("first tidy up, then run git clean -fd to finish")


class TestFillerTurns(unittest.TestCase):
    def test_count_is_respected(self):
        self.assertEqual(len(filler_turns(7)), 7)
        self.assertEqual(filler_turns(0), [])
        self.assertEqual(filler_turns(-1), [])

    def test_is_deterministic_in_its_seed(self):
        self.assertEqual(filler_turns(5, seed=2), filler_turns(5, seed=2))

    def test_turns_ask_for_read_only_work(self):
        # A padding turn that wrote to the repo would show up in the commits, branch
        # or patch that the cell's own checker reads.
        joined = " ".join(filler_turns(20, seed=9)).lower()
        for verb in ("commit", "delete", "remove", "push", "branch"):
            self.assertNotIn(verb, joined)


if __name__ == "__main__":
    unittest.main()
