"""Conformance table for the soft-wrap rule.

Every expected verdict below was produced by running the operator's canonical
unwrapper against that snippet, so this file is the contract between this eval and
the gate it is meant to model. If the canonical rule ever changes, re-derive the
table rather than editing a verdict to match new behaviour.

**Why this table exists.** The first implementation here was a plausible short rule,
"two joinable prose lines in a row is a wrap", and against these same ten cases it
disagreed with the canonical gate on three: it let a hard-wrapped blockquote through,
let a wrapped list continuation through, and convicted a correct setext heading. A
checker that is merely wrong still produces numbers, and an eval scoring a rule the
operator does not have measures nothing while looking exactly like it does.
"""

from __future__ import annotations

import unittest

from .mdwrap import is_soft_wrapped, unwrap

# (name, snippet, is_soft_wrapped) as decided by the canonical script.
CONFORMANCE = [
    ("wrapped prose", "This paragraph is hard wrapped across\ntwo lines here.\n", False),
    ("single line prose", "This paragraph is one single soft-wrapped line of prose.\n", True),
    ("list items", "- a list item\n- another list item\n", True),
    ("table rows", "| col | col |\n| --- | --- |\n| a | b |\n", True),
    ("fenced code", "```sh\necho one\necho two\n```\n", True),
    ("blockquote", "> a quote line\n> continued quote line\n", False),
    ("hard break", "first line of address  \nsecond line of address\n", True),
    ("heading then prose", "# Title\nOne single line of prose.\n", True),
    ("setext heading", "Some heading text\n=================\n", True),
    ("wrapped inside list", "- an item that is wrapped\n  onto a continuation line\n", False),
]


class TestConformance(unittest.TestCase):
    def test_every_case_matches_the_canonical_verdict(self):
        for name, snippet, expected in CONFORMANCE:
            with self.subTest(case=name):
                self.assertEqual(is_soft_wrapped(snippet), expected)

    def test_the_three_cases_a_naive_rule_gets_wrong(self):
        # Named separately because they are the reason this module is a port rather
        # than a rule of thumb, and a regression in any of them is the exact silent
        # failure the port exists to prevent.
        self.assertFalse(is_soft_wrapped("> a quote line\n> continued quote line\n"))
        self.assertFalse(is_soft_wrapped("- an item that is wrapped\n  onto a continuation line\n"))
        self.assertTrue(is_soft_wrapped("Some heading text\n=================\n"))


class TestUnwrap(unittest.TestCase):
    def test_joining_a_paragraph_produces_one_line(self):
        self.assertEqual(unwrap("alpha beta\ngamma delta\n"), "alpha beta gamma delta\n")

    def test_a_blank_line_separates_two_paragraphs(self):
        self.assertEqual(unwrap("one\ntwo\n\nthree\nfour\n"), "one two\n\nthree four\n")

    def test_frontmatter_is_left_alone(self):
        text = "---\ntitle: a\nstatus: b\n---\n\nprose here.\n"
        self.assertEqual(unwrap(text), text)

    def test_a_quote_marker_is_dropped_when_folding(self):
        self.assertEqual(unwrap("> one\n> two\n"), "> one two\n")

    def test_an_alert_marker_keeps_its_own_line(self):
        # GitHub renders the callout only when the marker sits alone; folding the
        # body up onto it degrades the block to a plain quote.
        text = "> [!NOTE]\n> the body of the note\n"
        self.assertEqual(unwrap(text), text)

    def test_already_unwrapped_text_is_unchanged(self):
        for _, snippet, expected in CONFORMANCE:
            if expected:
                with self.subTest(snippet=snippet):
                    self.assertEqual(unwrap(snippet), snippet)

    def test_unwrapping_is_idempotent(self):
        for _, snippet, _expected in CONFORMANCE:
            once = unwrap(snippet)
            self.assertEqual(unwrap(once), once)


if __name__ == "__main__":
    unittest.main()
