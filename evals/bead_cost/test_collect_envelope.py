"""The envelope reader must survive anything printed around the envelope.

The run that produced this test wrote `mise … tools: claude@2.1.233` on the first line of stdout and
the strict reader returned None for it, which the record carried as `usage: null` - a whole arm's
token and cost columns emptied while every run in it passed its verdict. Whether that line appears
depends on what the jail's tool cache already holds, so it is not reproducible on demand and cannot
be fixed by asking the harness to be quiet.
"""
import json
import pathlib
import tempfile
import unittest

import collect


ENVELOPE = {
    "is_error": False,
    "num_turns": 74,
    "stop_reason": "end_turn",
    "total_cost_usd": 3.9846327,
    "usage": {
        "input_tokens": 120,
        "output_tokens": 35059,
        "cache_read_input_tokens": 8391659,
        "cache_creation_input_tokens": 156815,
        "output_tokens_details": {"thinking_tokens": 20255},
    },
    "modelUsage": {"claude-sonnet-5": {}},
}

MISE = "mise /home/user/.config/mise/config.toml tools: claude@2.1.233"


class EnvelopeAroundNoise(unittest.TestCase):
    def stdout(self, text: str) -> pathlib.Path:
        handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        handle.write(text)
        handle.close()
        path = pathlib.Path(handle.name)
        self.addCleanup(path.unlink)
        return path

    def test_bare_envelope(self):
        usage = collect.read_claude_envelope(self.stdout(json.dumps(ENVELOPE)))
        self.assertEqual(usage["turns"], 74)

    def test_envelope_after_a_tool_activation_line(self):
        """The real failure: one line of noise ahead of the object."""
        usage = collect.read_claude_envelope(self.stdout(f"{MISE}\n{json.dumps(ENVELOPE)}"))
        self.assertIsNotNone(usage, "a line printed before the envelope must not empty the record")
        self.assertEqual(usage["turns"], 74)
        self.assertEqual(usage["output_tokens"], 35059)

    def test_envelope_before_trailing_noise(self):
        usage = collect.read_claude_envelope(self.stdout(f"{json.dumps(ENVELOPE)}\nwarning: whatever"))
        self.assertEqual(usage["turns"], 74)

    def test_pretty_printed_envelope_after_noise(self):
        """Spanning several lines, so a line-by-line reader alone would miss it."""
        usage = collect.read_claude_envelope(self.stdout(f"{MISE}\n{json.dumps(ENVELOPE, indent=2)}"))
        self.assertEqual(usage["turns"], 74)

    def test_agy_reader_shares_the_tolerance(self):
        envelope = {"status": "success", "num_turns": 1, "usage": {"output_tokens": 26647}}
        usage = collect.read_agy_envelope(self.stdout(f"{MISE}\n{json.dumps(envelope)}"))
        self.assertIsNotNone(usage)
        self.assertEqual(usage["output_tokens"], 26647)

    def test_no_envelope_is_still_absent(self):
        """Tolerant is not credulous: nothing parseable must stay None, never an empty dict."""
        self.assertIsNone(collect.read_claude_envelope(self.stdout("mise: nothing here\n")))
        self.assertIsNone(collect.read_claude_envelope(self.stdout("")))

    def test_a_json_object_without_usage_is_not_an_envelope(self):
        self.assertIsNone(collect.read_claude_envelope(self.stdout('{"hello": "world"}')))


if __name__ == "__main__":
    unittest.main()
