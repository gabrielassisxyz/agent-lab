"""The real CLI agent adapter: drive a coding-agent CLI and reduce its output into
the trajectory the runner expects.

The load-bearing, testable part is `parse_claude_stream`: turning a Claude Code
`--output-format stream-json` transcript into command/read/message events plus the
token accounting. That is pure and unit-tested against a fixture, so the reduction
logic is trustworthy without a model call. `ClaudeCliAgent.run` is the thin
integration around it: it shells out to `claude -p`, captures the stream, and parses
it. It does a real model call, so it is never exercised in CI; the parser is what
the tests cover.

Multi-turn works by session resume. Turn 0 is a plain `claude -p`, whose events
carry a session id; every later turn passes `--resume <id>` so the model sees the
accumulated conversation. That is what makes the distance axis real: a rule stated
at turn 0 and a task issued at turn 50 are separated by an actual conversation, not
by a few lines of prompt text.

Only Claude Code is wired here. A second adapter (pi, codex, agy) is the same shape:
run the CLI, map its events to the three event types, read its usage report.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .agent import AgentRun, Event
from .schema import Usage

# Tool names whose invocation we record. Bash -> a command; Read -> a file read.
# Other tools (Edit, Write, Grep) leave their trace in the repo diff, which the
# runner reads separately, so they need no event here.
_BASH_TOOLS = frozenset({"Bash"})
_READ_TOOLS = frozenset({"Read"})


@dataclass(frozen=True)
class ParsedStream:
    """What one CLI invocation yields: the trajectory, the cost, and the handle
    needed to continue the conversation on the next turn.
    """

    events: list[Event] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    session_id: str | None = None
    is_error: bool = False


def parse_claude_stream(lines: Iterable[str]) -> ParsedStream:
    """Reduce a Claude Code stream-json transcript into ordered events plus usage.

    Recognizes assistant `tool_use` blocks (Bash -> command, Read -> read) in the
    order they appear, and emits a single final message event carrying the run's
    result text (the `result` line if present, else the last assistant text). Lines
    that are blank or not valid JSON are skipped, so a stray log line cannot break
    the parse.
    """
    events: list[Event] = []
    result_text: str | None = None
    last_assistant_text: str = ""
    usage = Usage()
    session_id: str | None = None
    is_error = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if session_id is None and isinstance(obj.get("session_id"), str):
            session_id = obj["session_id"]

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
            usage = usage + _usage_from(obj.get("usage", {}))
            is_error = bool(obj.get("is_error", False))

    final_text = result_text if result_text is not None else last_assistant_text
    events.append({"type": "message", "text": final_text})
    return ParsedStream(events=events, usage=usage, session_id=session_id, is_error=is_error)


def _usage_from(raw: dict) -> Usage:
    """Read the CLI's own token report. An absent key stays zero rather than being
    guessed: a fabricated cost corrupts every comparison that reads it.
    """
    return Usage(
        input_tokens=int(raw.get("input_tokens", 0) or 0),
        output_tokens=int(raw.get("output_tokens", 0) or 0),
        cache_read_tokens=int(raw.get("cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(raw.get("cache_creation_input_tokens", 0) or 0),
    )


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
    """Drive `claude -p` in the repo, one invocation per turn, and parse each stream.
    Real model call, so this is never run in CI. `extra_args` lets a caller pass
    model, permission and sandbox flags without this adapter hardcoding a policy.
    """

    model: str | None = None
    timeout_s: int = 900
    extra_args: list[str] = field(default_factory=list)
    # Run with the operator's own customizations disabled. A cell only measures the
    # injected corpus if the injected corpus is the only rule set present, and by
    # default this CLI loads the user's global instructions. In the first baseline
    # sweep that leaked a standing "always work in a worktree" rule into every arm,
    # including the control, and it is what produced the run's only failure mode.
    # This is the same hermeticity the runner already enforces for git hooks.
    isolate: bool = True

    def resume_from(self, session_id: str, turns: list[str], repo_dir: Path,
                    env: dict[str, str] | None = None) -> AgentRun:
        """Drive turns against an existing session instead of opening a new one.

        This is what makes a seeded cell cost one call rather than N: the padding
        turns already happened in a recording, and the cell resumes a clone of it to
        issue only the turn a checker reads. `recording.seed` produces the id.
        """
        return self.run(turns, repo_dir, env=env, session_id=session_id)

    def run(self, turns: list[str], repo_dir: Path,
            env: dict[str, str] | None = None,
            session_id: str | None = None) -> AgentRun:
        events: list[Event] = []
        usage = Usage()
        last = len(turns) - 1

        for index, turn in enumerate(turns):
            try:
                proc = subprocess.run(
                    self._command(turn, session_id), cwd=repo_dir, env=env,
                    capture_output=True, text=True, timeout=self.timeout_s,
                )
            except subprocess.TimeoutExpired:
                return AgentRun(events, usage, error=f"timeout on turn {index}")

            if proc.returncode != 0:
                tail = (proc.stderr or "").strip().splitlines()
                return AgentRun(events, usage, error=(
                    f"exit {proc.returncode} on turn {index}: {tail[-1] if tail else ''}"))

            parsed = parse_claude_stream(proc.stdout.splitlines())
            usage = usage + parsed.usage
            if parsed.is_error:
                return AgentRun(events, usage, error=f"agent reported an error on turn {index}")

            # Only the closing message of the last turn is what a checker reads, so
            # intermediate message events are dropped. Their commands are not: a
            # destructive command run at turn 3 still counts against the agent.
            events.extend(parsed.events if index == last
                          else [e for e in parsed.events if e.get("type") != "message"])

            session_id = session_id or parsed.session_id
            if session_id is None and index < last:
                return AgentRun(events, usage,
                                error=f"no session id after turn {index}; cannot continue")

        return AgentRun(events=events, usage=usage, session_id=session_id)

    def _command(self, turn: str, session_id: str | None) -> list[str]:
        cmd = ["claude", "-p", turn, "--output-format", "stream-json", "--verbose"]
        if self.isolate:
            cmd.append("--safe-mode")
        if session_id:
            cmd += ["--resume", session_id]
        if self.model:
            cmd += ["--model", self.model]
        return cmd + self.extra_args
