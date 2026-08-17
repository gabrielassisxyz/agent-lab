"""The aggregator's own failure modes, which are the quiet kind.

A review aggregator is trusted precisely when nobody re-reads the answers, so the failures worth
testing are the ones that still print a well-formed table: a reviewer dropped for answering in the
wrong wrapper, a panel that shrank without saying so, a validity verdict that never fires. The
disposable dry-run that exercised this file before proved the last of those and then vanished with
its scratchpad; this is the version that survives a change to the code it checks.
"""

import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import aggregate_review  # noqa: E402
from aggregate_review import load_json, unwrap_envelope  # noqa: E402

RANKING = {"ranking": ["E", "A", "B", "C", "D"], "confidence": "high"}
KEY = {
    "seed": 1,
    "mapping": {"A": "kimi / r1", "B": "sonnet / r2", "C": "gemini-3.7-flash / r3",
                "D": "deepseek / r4", "E": "reference commit abc1234"},
    "reference_letter": "E",
}


class Envelope(unittest.TestCase):
    """The wrapper `agy` puts around an answer is a valid dict with none of the answer's keys."""

    def test_answer_carried_as_a_json_string_in_response(self):
        env = {"status": "SUCCESS", "response": json.dumps(RANKING)}
        self.assertEqual(RANKING, unwrap_envelope(env))

    def test_answer_carried_as_an_object_in_structured_output(self):
        env = {"status": "SUCCESS", "response": "", "structured_output": RANKING}
        self.assertEqual(RANKING, unwrap_envelope(env))

    def test_a_plain_answer_is_left_alone(self):
        self.assertEqual(RANKING, unwrap_envelope(dict(RANKING)))

    def test_an_envelope_with_nothing_in_it_is_not_mistaken_for_an_answer(self):
        env = {"status": "SUCCESS", "response": ""}
        self.assertIsNone(unwrap_envelope(env).get("ranking"))

    def test_load_json_reaches_through_the_envelope(self):
        raw = "mise WARN noise\n" + json.dumps({"status": "SUCCESS", "response": json.dumps(RANKING)})
        self.assertEqual(RANKING["ranking"], load_json(raw)["ranking"])


def write_panel(tmp: pathlib.Path, rankings: dict[str, list[str]], envelope: set[str] = frozenset()):
    answers = tmp / "answers"
    answers.mkdir(parents=True, exist_ok=True)
    for reviewer, order in rankings.items():
        body = json.dumps({"ranking": order, "confidence": "high"})
        if reviewer in envelope:
            body = json.dumps({"status": "SUCCESS", "response": body})
        (answers / f"passB-{reviewer}.txt").write_text(body)
    key = tmp / "key.json"
    key.write_text(json.dumps(KEY))
    return answers, key


def run(answers: pathlib.Path, key: pathlib.Path) -> tuple[int, str]:
    argv = sys.argv
    sys.argv = ["aggregate_review.py", str(answers), "--key", str(key)]
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            code = aggregate_review.main()
    finally:
        sys.argv = argv
    return code, buffer.getvalue()


class Verdict(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.tmp = pathlib.Path(self._dir.name)

    def test_a_healthy_panel_passes_and_places_the_reference_first(self):
        answers, key = write_panel(self.tmp, {
            "codex": ["E", "A", "B", "C", "D"],
            "glm": ["E", "A", "C", "B", "D"],
            "opus": ["E", "B", "A", "C", "D"],
        })
        code, out = run(answers, key)
        self.assertEqual(0, code)
        self.assertIn("no invalidating condition triggered", out)
        self.assertIn("1. E", out)

    def test_the_reference_ranked_last_invalidates_the_result(self):
        answers, key = write_panel(self.tmp, {
            "codex": ["A", "B", "C", "D", "E"],
            "glm": ["A", "B", "C", "D", "E"],
        })
        code, out = run(answers, key)
        self.assertEqual(2, code)
        self.assertIn("ranked LAST", out)
        self.assertIn("must not be published", out)

    def test_an_envelope_answer_still_counts_as_a_reviewer(self):
        answers, key = write_panel(self.tmp, {
            "codex": ["E", "A", "B", "C", "D"],
            "glm": ["E", "A", "C", "B", "D"],
            "gemini": ["E", "C", "A", "B", "D"],
        }, envelope={"gemini"})
        code, out = run(answers, key)
        self.assertEqual(0, code)
        self.assertIn("'gemini'", out)
        self.assertIn("3 usable ranking(s)", out)

    def test_a_reviewer_that_answered_nothing_is_named_in_the_verdict(self):
        answers, key = write_panel(self.tmp, {
            "codex": ["E", "A", "B", "C", "D"],
            "glm": ["E", "A", "C", "B", "D"],
        })
        (answers / "passB-gemini.txt").write_text(
            json.dumps({"status": "SUCCESS", "response": ""}))
        code, out = run(answers, key)
        self.assertEqual(0, code)
        self.assertIn("MISSING from the ranking", out)
        self.assertIn("gemini", out)


if __name__ == "__main__":
    unittest.main()
