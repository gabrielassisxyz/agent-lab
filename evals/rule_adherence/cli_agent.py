"""The real CLI agent adapter (Phase 1b): drive a coding-agent CLI and reduce its
output into the event stream the runner expects.

The load-bearing, testable part is `parse_claude_stream`: turning a Claude Code
`--output-format stream-json` transcript into command/read/message events. That is
pure and unit-tested against a fixture, so the reduction logic is trustworthy
without a model call. `ClaudeCliAgent.run` is the thin integration around it: it
shells out to `claude -p`, captures the stream, and parses it. It does a real model
call, so it is never exercised in CI; the parser is what the tests cover.

Only Claude Code is wired first because its stream format is the best documented. A
second adapter (pi, codex) is the same shape: run the CLI, map its events to the
three event types.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .agent import Event

# Tool names whose invocation we record. Bash -> a command; Read -> a file read.
# Other tools (Edit, Write, Grep) leave their trace in the repo diff, which the
# runner reads separately, so they need no event here.
_BASH_TOOLS = frozenset({"Bash"})
_READ_TOOLS = frozenset({"Read"})


def parse_claude_stream(lines: Iterable[str]) -> list[Event]:
    """Reduce a Claude Code stream-json transcript into ordered events.

    Recognizes assistant `tool_use` blocks (Bash -> command, Read -> read) in the
    order they appear, and emits a single final message event carrying the run's
    result text (the `result` line if present, else the last assistant text). Lines
    that are blank or not valid JSON are skipped, so a stray log line cannot break
    the parse.
    """
    events: list[Event] = []
    result_text: str | None = None
    last_assistant_text: str = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = obj.get("type")
        if kind == "assistant":
            for block in obj.get("message", {}).get("content", []):
                btype = block.get("type")
                if btype == "text":
                    last_assistant_text = block.get("text", last_assistant_text)
                elif btype == "tool_use":
                    event = _tool_event(block)
                    if event is not None:
                        events.append(event)
        elif kind == "result":
            result_text = obj.get("result", result_text)

    final_text = result_text if result_text is not None else last_assistant_text
    events.append({"type": "message", "text": final_text})
    return events


def _tool_event(block: dict) -> Event | None:
    name = block.get("name", "")
    args = block.get("input", {})
    if name in _BASH_TOOLS:
        return {"type": "command", "command": args.get("command", "")}
    if name in _READ_TOOLS:
        return {"type": "read", "path": args.get("file_path", args.get("path", ""))}
    return None


@dataclass
class ClaudeCliAgent:
    """Drive `claude -p` in the repo and parse its stream. Real model call, so this
    is never run in CI. `extra_args` lets a caller pass model, permission and sandbox
    flags without this adapter hardcoding a policy.
    """

    model: str | None = None
    timeout_s: int = 900
    extra_args: list[str] = field(default_factory=list)

    def run(self, prompt: str, repo_dir: Path) -> list[Event]:
        cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose"]
        if self.model:
            cmd += ["--model", self.model]
        cmd += self.extra_args
        proc = subprocess.run(
            cmd, cwd=repo_dir, capture_output=True, text=True, timeout=self.timeout_s
        )
        return parse_claude_stream(proc.stdout.splitlines())
