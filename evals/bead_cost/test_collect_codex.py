"""The codex lane's usage reader, pinned against the three ways it reads a run wrongly.

Every fixture below is trimmed from a real `codex exec --json` run rather than imagined, because
the shape is the whole difficulty: this harness streams one JSON object per LINE and the envelope
readers beside it expect one object per FILE, so the tolerant reader they share returns the run's
first event - which parses perfectly and carries no usage at all.
"""
import json
import pathlib
import tempfile
import unittest

import collect


# The stream on stdout: several events, usage only on the last one.
STREAM = "\n".join(json.dumps(event) for event in [
    {"type": "thread.started", "thread_id": "01a0105d-e125-7321-83d1-b5391b1b876f"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"type": "reasoning"}},
    {"type": "turn.completed", "usage": {
        "input_tokens": 41829,
        "cached_input_tokens": 37120,
        "cache_write_input_tokens": 0,
        "output_tokens": 341,
        "reasoning_output_tokens": 9,
    }},
])

MISE = "mise /home/user/.config/mise/config.toml tools: codex@0.147.0"


def token_count(total_out: int, last_out: int) -> dict:
    return {"timestamp": "2026-08-17T15:36:33.587Z", "type": "event_msg", "payload": {
        "type": "token_count",
        "info": {
            "total_token_usage": {"input_tokens": 41829, "cached_input_tokens": 37120,
                                  "cache_write_input_tokens": 0, "output_tokens": total_out,
                                  "reasoning_output_tokens": 9},
            "last_token_usage": {"input_tokens": 14214, "output_tokens": last_out},
        },
    }}


ROLLOUT = [
    {"type": "session_meta", "payload": {"session_id": "01a0105d", "cli_version": "0.147.0"}},
    {"type": "turn_context", "payload": {"model": "gpt-5.6-terra", "effort": "medium",
                                         "sandbox_policy": {"type": "danger-full-access"}}},
    token_count(143, 143),
    {"type": "response_item", "payload": {"type": "custom_tool_call"}},
    token_count(269, 126),
    token_count(341, 72),
    {"type": "event_msg", "payload": {"type": "task_complete"}},
]


class CodexUsage(unittest.TestCase):
    def run_dir(self, stdout_text: str, rollout: list | None = ROLLOUT) -> tuple:
        root = pathlib.Path(tempfile.mkdtemp())
        (root / "stdout.txt").write_text(stdout_text)
        home = root / "home"
        sessions = home / ".codex" / "sessions" / "2026" / "08" / "17"
        sessions.mkdir(parents=True)
        if rollout is not None:
            (sessions / "rollout-2026-08-17T12-36-23.jsonl").write_text(
                "\n".join(json.dumps(event) for event in rollout) + "\n")
        return root / "stdout.txt", home

    def test_usage_comes_off_the_last_event_of_the_stream(self):
        stdout, home = self.run_dir(STREAM)
        usage = collect.read_codex_stream(stdout, home)
        self.assertEqual(usage["output_tokens"], 341)
        self.assertEqual(usage["input_tokens"], 41829)
        self.assertEqual(usage["cache_read_tokens"], 37120)
        self.assertEqual(usage["reasoning_tokens"], 9)

    def test_a_line_of_tool_noise_ahead_of_the_stream_changes_nothing(self):
        stdout, home = self.run_dir(f"{MISE}\n{STREAM}")
        usage = collect.read_codex_stream(stdout, home)
        self.assertIsNotNone(usage)
        self.assertEqual(usage["output_tokens"], 341)

    def test_turns_count_model_calls_not_the_single_closing_event(self):
        """The failure this exists to stop: `turn.completed` fires ONCE, so counting it reports 1
        for a run of any length - a column constant across the dimension it should vary on, which
        is the shape that already emptied the agy lane's turn count once."""
        stdout, home = self.run_dir(STREAM)
        usage = collect.read_codex_stream(stdout, home)
        self.assertEqual(usage["turns"], 3)

    def test_the_effort_reported_is_the_one_the_run_actually_used(self):
        stdout, home = self.run_dir(STREAM)
        usage = collect.read_codex_stream(stdout, home)
        self.assertEqual(usage["reasoning_effort_ran"], "medium")
        self.assertEqual(usage["model_ran"], "gpt-5.6-terra")

    def test_a_truncated_stream_falls_back_to_the_rollout_total(self):
        """A run killed mid-flight still spent its tokens, and they are still on disk."""
        truncated = STREAM.split('{"type": "turn.completed"')[0]
        stdout, home = self.run_dir(truncated)
        usage = collect.read_codex_stream(stdout, home)
        self.assertIsNotNone(usage, "tokens recoverable from the rollout must not be reported absent")
        self.assertEqual(usage["output_tokens"], 341)
        self.assertIn("rollout", usage["usage_source"])

    def test_nothing_measurable_stays_absent(self):
        """Tolerant is not credulous. No stream and no rollout is None, never a record of zeros."""
        stdout, home = self.run_dir("mise: nothing here\n", rollout=None)
        self.assertIsNone(collect.read_codex_stream(stdout, home))

    def test_the_agy_reader_would_be_wrong_here_rather_than_empty(self):
        """Why the dispatch in main() is by name, and why the danger is not a crash.

        The shared envelope reader does find codex's closing event, and that event does carry a
        `usage` dict - so the agy reader returns a record rather than None. It is the FIELD NAMES
        that differ: codex writes `cached_input_tokens` and `reasoning_output_tokens` where agy
        writes `cache_read_tokens` and `thinking_tokens`, and it has no `num_turns` at all. The
        result is a well-formed record, right in the two fields the harnesses happen to share and
        silently empty in the rest - which is the failure shape this experiment keeps meeting.
        """
        stdout, _ = self.run_dir(STREAM)
        wrong = collect.read_agy_envelope(stdout)
        self.assertIsNotNone(wrong, "the shared reader parses this stream, which is the problem")
        self.assertEqual(wrong["output_tokens"], 341)
        self.assertIsNone(wrong["turns"])
        self.assertIsNone(wrong["cache_read_tokens"])
        self.assertIsNone(wrong["reasoning_tokens"])


if __name__ == "__main__":
    unittest.main()
