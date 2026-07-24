"""Tests for the CLI-agent output parser and the experiment entrypoint.

`parse_claude_stream` is the load-bearing logic that turns a real agent's transcript
into events; it is tested here against a fixture stream so the reduction is trusted
without a model call. `run_and_report` is tested through the fake-agent path, so the
end-to-end entrypoint (matrix, scoring, results file) is covered too. `ClaudeCliAgent.run`
itself makes a real model call and is not exercised.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from .agent import FakeAgent
from .cli_agent import parse_claude_stream
from .run import run_and_report


def _stream(*objs: dict) -> list[str]:
    return [json.dumps(o) for o in objs]


class TestParseClaudeStream(unittest.TestCase):
    def test_extracts_commands_reads_and_result(self):
        lines = _stream(
            {"type": "system", "subtype": "init"},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "let me look"},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "AGENTS.md"}},
            ]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "rm stray.tmp"}},
            ]}},
            {"type": "result", "subtype": "success", "result": "Removed the stray file."},
        )
        events = parse_claude_stream(lines)
        self.assertEqual(events, [
            {"type": "read", "path": "AGENTS.md"},
            {"type": "command", "command": "rm stray.tmp"},
            {"type": "message", "text": "Removed the stray file."},
        ])

    def test_preserves_command_order_across_messages(self):
        lines = _stream(
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "first"}}]}},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Bash", "input": {"command": "second"}}]}},
        )
        commands = [e["command"] for e in parse_claude_stream(lines) if e["type"] == "command"]
        self.assertEqual(commands, ["first", "second"])

    def test_ignores_other_tools_and_falls_back_to_last_text(self):
        lines = _stream(
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "x"}},
                {"type": "text", "text": "done editing"},
            ]}},
        )
        events = parse_claude_stream(lines)
        self.assertEqual(events, [{"type": "message", "text": "done editing"}])

    def test_skips_blank_and_non_json_lines(self):
        events = parse_claude_stream(["", "not json", json.dumps(
            {"type": "result", "result": "ok"})])
        self.assertEqual(events, [{"type": "message", "text": "ok"}])


class TestRunAndReport(unittest.TestCase):
    def test_writes_a_results_document(self):
        agent_for = lambda task, placement: FakeAgent(
            commands=["true"], final_text="did nothing destructive")
        with tempfile.TemporaryDirectory() as tmp:
            out = run_and_report(agent_for, pathlib.Path(tmp), reps=1, placements=("hybrid",))
            self.assertTrue(out.exists())
            doc = json.loads(out.read_text())
            self.assertIn("runs", doc)
            self.assertIn("scores", doc)
            self.assertTrue(doc["runs"])


if __name__ == "__main__":
    unittest.main()
