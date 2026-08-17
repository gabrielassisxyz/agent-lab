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


# What `codex exec` writes: the whole prompt echoed back - example JSON and all - then the answer,
# then a token tally. Three traps live in here at once. The example is NOT valid JSON, because the
# shape is written with alternatives; the echoed packet is Go source, with braces and quotes of its
# own in quantity; and the LAST parseable object in the file is `reasons[0]`, nested inside the
# answer rather than being it.
CODEX_TRANSCRIPT = """OpenAI Codex v0.147.0
user
Return ONLY a JSON object matching this shape:

```json
{
  "ranking": ["B", "D", "A", "C", "E"],
  "confidence": "high" | "medium" | "low"
}
```

THE IMPLEMENTATIONS:
+func (c *Coordinator) Reserve(a string) (*Lease, error) {
+	if c.pending[a] >= 60 {
+		return nil, errors.New("rate ceiling reached for \\"account\\"")
+	}
+	return &Lease{owner: a}, nil
+}
codex
{
  "ranking": ["C", "A", "E", "D", "B"],
  "reasons": [
    {"impl": "C", "position": 1, "why": "keeps the lease where it is created"}
  ],
  "confidence": "high"
}
tokens used
31,819
"""

# What `agy` writes: one object, and it carries back a copy of the schema it was handed. That copy
# has a `properties` object whose KEYS are the answer's keys, and it sits AFTER the response in the
# file - so a backwards search reaches the schema first and comes back holding {"type": "array"}.
AGY_ENVELOPE = json.dumps({
    "conversation_id": "abc",
    "status": "SUCCESS",
    "response": json.dumps({"ranking": ["D", "B", "E", "A", "C"], "confidence": "high"}),
    "json_schema": {"type": "object", "required": ["ranking"],
                    "properties": {"ranking": {"type": "array"},
                                   "confidence": {"type": "string"}}},
    "usage": {"total_tokens": 18299},
})


# The same transcript with the one difference that makes the search direction matter: the echoed
# example is VALID JSON. Today's prompts write the shape with alternatives, so the example happens
# not to parse and reading forwards gives the same answer as reading backwards - checked against all
# fourteen real transcripts, zero divergence. That is an accident of how the shape is written, not a
# defence. Tidy the example into something valid, which is an ordinary thing for someone to do, and
# a forward search returns the EXAMPLE's ranking as though a reviewer had produced it: not an error
# anybody would see, but a fabricated result.
CODEX_TRANSCRIPT_VALID_EXAMPLE = CODEX_TRANSCRIPT.replace(
    '"confidence": "high" | "medium" | "low"', '"confidence": "high"')


class Transcript(unittest.TestCase):
    def test_a_valid_example_in_the_echoed_prompt_is_still_not_the_answer(self):
        answer = load_json(CODEX_TRANSCRIPT_VALID_EXAMPLE, "ranking")
        self.assertEqual(["C", "A", "E", "D", "B"], answer["ranking"])
        self.assertNotEqual(["B", "D", "A", "C", "E"], answer["ranking"])

    def test_the_answer_is_read_out_of_a_codex_transcript(self):
        answer = load_json(CODEX_TRANSCRIPT, "ranking")
        self.assertEqual(["C", "A", "E", "D", "B"], answer["ranking"])

    def test_the_nested_reason_is_not_mistaken_for_the_answer(self):
        # `reasons[0]` is the last object in the file and parses perfectly on its own.
        answer = load_json(CODEX_TRANSCRIPT, "ranking")
        self.assertNotIn("impl", answer)

    def test_the_schema_echoed_back_by_agy_is_not_mistaken_for_the_answer(self):
        answer = load_json("mise WARN noise\n" + AGY_ENVELOPE, "ranking")
        self.assertEqual(["D", "B", "E", "A", "C"], answer["ranking"])

    def test_an_agy_envelope_with_an_empty_response_yields_nothing(self):
        empty = json.dumps({"status": "SUCCESS", "response": "",
                            "json_schema": {"properties": {"ranking": {"type": "array"}}}})
        self.assertIsNone(load_json(empty, "ranking"))

    def test_a_transcript_with_no_object_at_all_is_none(self):
        self.assertIsNone(load_json("no json here, only regret", "ranking"))


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

    def test_the_reference_ranked_last_is_flagged_and_still_publishes(self):
        # It used to invalidate, on the assumption that the reference was known-good. It was not:
        # that commit came out of the same kind of agent run as the candidates. So the panel putting
        # it last is a claim about that implementation, and discarding the review over it would
        # throw away the answer for disagreeing with the thing it was asked to judge.
        answers, key = write_panel(self.tmp, {
            "codex": ["A", "B", "C", "D", "E"],
            "glm": ["A", "B", "C", "D", "E"],
        })
        code, out = run(answers, key)
        self.assertEqual(0, code)
        self.assertIn("ATTENTION", out)
        self.assertIn("ranked LAST", out)
        self.assertNotIn("must not be published", out)

    def test_a_missing_conflict_free_reviewer_invalidates_the_ranking(self):
        answers, key = write_panel(self.tmp, {
            "codex": ["E", "A", "B", "C", "D"],
            "opus": ["E", "B", "A", "C", "D"],
            "gemini": ["E", "C", "A", "B", "D"],
        })
        code, out = run(answers, key)
        self.assertEqual(2, code)
        self.assertIn("conflict-free reviewer is missing", out)
        self.assertIn("must not be published", out)

    def test_a_missing_conflicted_reviewer_is_flagged_and_still_publishes(self):
        answers, key = write_panel(self.tmp, {
            "codex": ["E", "A", "B", "C", "D"],
            "glm": ["E", "A", "C", "B", "D"],
            "opus": ["E", "B", "A", "C", "D"],
        })
        (answers / "passB-gemini.txt").write_text(json.dumps({"status": "SUCCESS", "response": ""}))
        code, out = run(answers, key)
        self.assertEqual(0, code)
        self.assertIn("ATTENTION", out)
        self.assertIn("gemini", out)

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

    def test_reviewers_that_scatter_still_invalidate(self):
        # The check that survives the reference losing its status: agreement between reviewers is
        # independent of whether the reference was any good.
        answers, key = write_panel(self.tmp, {
            "codex": ["E", "A", "B", "C", "D"],
            "glm": ["D", "C", "B", "A", "E"],
        })
        code, out = run(answers, key)
        self.assertEqual(2, code)
        self.assertIn("do not correlate", out)


if __name__ == "__main__":
    unittest.main()
