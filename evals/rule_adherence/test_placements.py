"""Unit tests for the placement composer and the classify-by-category matcher."""

from __future__ import annotations

import pathlib
import unittest

from .placements import (
    PLACEMENTS,
    compose,
    enforces_gate,
    load_corpus,
    relevant_rules,
)

_CORPUS = load_corpus(pathlib.Path(__file__).parent / "corpus.sample.json")


class TestRelevantRules(unittest.TestCase):
    def test_matches_by_category(self):
        got = {r.id for r in relevant_rules("non-standard-conventions", _CORPUS)}
        self.assertEqual(got, {"conventional-commits", "conventional-branch"})

    def test_no_match_is_empty(self):
        self.assertEqual(relevant_rules("memory-state", _CORPUS), [])


class TestCompose(unittest.TestCase):
    def test_front_load_all_puts_every_rule_in_prefix(self):
        c = compose("do X", "safety-critical", "front-load-all", _CORPUS)
        for rule in _CORPUS:
            self.assertIn(rule.text, c.prefix)
        self.assertEqual(c.tail, "")

    def test_pruned_static_keeps_only_the_constitution(self):
        c = compose("do X", "non-standard-conventions", "pruned-static", _CORPUS)
        self.assertIn("destructive git", c.prefix)              # safety-critical is in
        self.assertNotIn("Conventional Commits", c.prefix)      # conventions are out
        self.assertEqual(c.tail, "")

    def test_jit_puts_task_rules_in_the_tail_only(self):
        c = compose("do X", "non-standard-conventions", "jit-near-query", _CORPUS)
        self.assertEqual(c.prefix, "")
        self.assertIn("Conventional Commits", c.tail)

    def test_hybrid_has_constitution_prefix_and_task_tail(self):
        c = compose("do X", "non-standard-conventions", "hybrid", _CORPUS)
        self.assertIn("destructive git", c.prefix)
        self.assertIn("Conventional Commits", c.tail)

    def test_render_places_tail_after_instruction(self):
        c = compose("THE_TASK", "non-standard-conventions", "jit-near-query", _CORPUS)
        rendered = c.render()
        self.assertLess(rendered.index("THE_TASK"), rendered.index("Conventional Commits"))

    def test_unknown_placement_raises(self):
        with self.assertRaises(ValueError):
            compose("x", "safety-critical", "no-such-placement", _CORPUS)

    def test_all_placements_compose(self):
        for p in PLACEMENTS:
            self.assertTrue(compose("x", "safety-critical", p, _CORPUS).render())


class TestEnforcement(unittest.TestCase):
    def test_only_hybrid_enforcement_gates(self):
        self.assertTrue(enforces_gate("hybrid-enforcement"))
        for p in ("front-load-all", "pruned-static", "jit-near-query", "hybrid"):
            self.assertFalse(enforces_gate(p))


if __name__ == "__main__":
    unittest.main()
