"""Unit tests for the placement composer, the classify-by-category matcher, and the
distance axes.

The composer now returns a session (a list of turns) rather than a single prompt, so
the assertions are about where rule text lands in that session: turn 0 for a static
prefix, the last turn for a just-in-time tail. The axis tests are the ones that
matter most, because a composer that quietly ignored `Axes` would put the experiment
right back where the first run was: five arms, no distance, no signal.
"""

from __future__ import annotations

import pathlib
import unittest

from .placements import (
    CONTROL,
    PLACEMENTS,
    Axes,
    compose,
    enforces_gate,
    load_corpus,
    relevant_rules,
)

_CORPUS = load_corpus(pathlib.Path(__file__).parent / "corpus.sample.json")


def _first(session):
    return session.turns[0]


def _last(session):
    return session.turns[-1]


class TestRelevantRules(unittest.TestCase):
    def test_matches_by_category(self):
        # Asserted by category rather than by rule id: the corpus is meant to be
        # replaced (it is an input to the experiment, not part of it), and a test
        # pinned to the ids of one snapshot fails on every swap without ever having
        # checked the matcher.
        got = relevant_rules("non-standard-conventions", _CORPUS)
        self.assertTrue(got)
        for rule in got:
            self.assertEqual(rule.category, "non-standard-conventions")

    def test_every_category_in_the_corpus_is_retrievable(self):
        for rule in _CORPUS:
            self.assertIn(rule, relevant_rules(rule.category, _CORPUS))

    def test_no_match_is_empty(self):
        self.assertEqual(relevant_rules("no-such-category", _CORPUS), [])


class TestCompose(unittest.TestCase):
    def test_front_load_all_puts_every_rule_in_prefix(self):
        session = compose("do X", "safety-critical", "front-load-all", _CORPUS)
        for rule in _CORPUS:
            self.assertIn(rule.text, _first(session))

    def test_pruned_static_keeps_only_the_constitution(self):
        session = compose("do X", "non-standard-conventions", "pruned-static", _CORPUS)
        self.assertIn("destructive git", _first(session))          # safety-critical is in
        self.assertNotIn("Conventional Commits", _first(session))  # conventions are out

    def test_jit_puts_task_rules_after_the_instruction(self):
        session = compose("THE_TASK", "non-standard-conventions", "jit-near-query", _CORPUS)
        turn = _last(session)
        self.assertLess(turn.index("THE_TASK"), turn.index("Conventional Commits"))

    def test_hybrid_has_constitution_prefix_and_task_tail(self):
        session = compose("do X", "non-standard-conventions", "hybrid", _CORPUS)
        self.assertIn("destructive git", _first(session))
        self.assertIn("Conventional Commits", _last(session))

    def test_unknown_placement_raises(self):
        with self.assertRaises(ValueError):
            compose("x", "safety-critical", "no-such-placement", _CORPUS)

    def test_all_placements_compose(self):
        for p in PLACEMENTS:
            self.assertTrue(compose("x", "safety-critical", p, _CORPUS).render())


class TestControlArm(unittest.TestCase):
    def test_control_carries_no_rule_text(self):
        session = compose("do X", "safety-critical", CONTROL, _CORPUS)
        rendered = session.render()
        for rule in _CORPUS:
            self.assertNotIn(rule.text, rendered)

    def test_control_still_carries_the_instruction(self):
        self.assertIn("do X", compose("do X", "safety-critical", CONTROL, _CORPUS).render())


class TestAxes(unittest.TestCase):
    def test_more_turns_means_more_messages(self):
        session = compose("do X", "safety-critical", "hybrid", _CORPUS, Axes(turns=5))
        self.assertEqual(len(session.turns), 5)

    def test_the_task_always_arrives_last(self):
        session = compose("THE_TASK", "safety-critical", "hybrid", _CORPUS, Axes(turns=4))
        self.assertIn("THE_TASK", session.turns[-1])
        for earlier in session.turns[:-1]:
            self.assertNotIn("THE_TASK", earlier)

    def test_static_rules_stay_on_the_first_turn_when_the_session_is_long(self):
        session = compose("THE_TASK", "safety-critical", "pruned-static", _CORPUS, Axes(turns=6))
        self.assertIn("destructive git", session.turns[0])
        self.assertNotIn("destructive git", session.turns[-1])

    def test_filler_grows_the_session(self):
        short = compose("do X", "safety-critical", "hybrid", _CORPUS, Axes(filler_tokens=0))
        long = compose("do X", "safety-critical", "hybrid", _CORPUS, Axes(filler_tokens=2000))
        self.assertGreater(len(long.render()), len(short.render()) + 4000)

    def test_filler_is_identical_across_arms(self):
        # If a longer arm also carried more padding, any difference between arms
        # would confound placement with context length. Only the rules may move.
        axes = Axes(filler_tokens=500, turns=3)
        sizes = {
            p: len(compose("do X", "safety-critical", p, _CORPUS, axes).turns)
            for p in PLACEMENTS
        }
        self.assertEqual(len(set(sizes.values())), 1)

    def test_zero_turns_is_rejected(self):
        with self.assertRaises(ValueError):
            compose("x", "safety-critical", "hybrid", _CORPUS, Axes(turns=0))

    def test_axes_label_is_stable(self):
        self.assertEqual(Axes(turns=20, filler_tokens=8000).label(), "t20-f8000")


class TestEnforcement(unittest.TestCase):
    def test_only_hybrid_enforcement_gates(self):
        self.assertTrue(enforces_gate("hybrid-enforcement"))
        for p in (CONTROL, "front-load-all", "pruned-static", "jit-near-query", "hybrid"):
            self.assertFalse(enforces_gate(p))


if __name__ == "__main__":
    unittest.main()
