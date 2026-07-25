"""The agent adapter: the boundary between the runner and whatever produces a
trajectory.

An adapter takes a **session** (the ordered user turns of one cell) plus a staged
repo and returns everything observable about what the agent did. The runner never
knows which agent it drove, which is what lets the same experiment compare Claude
Code, pi, codex or a fake.

Why the protocol takes a list of turns rather than one prompt. The experiment's
central axis is how far a rule can sit from the moment it decides something and
still be followed, and distance is measured in turns as much as in tokens. A
single-turn cell is the degenerate case `turns=[prompt]`, so nothing is lost by
having one shape instead of two. The `env` parameter exists for the same
run-it-once reason: the enforcement gate and the command shim reach the agent
subprocess through its environment, and an adapter written against a signature
without it has to be rewritten the moment either lands.

`FakeAgent` is a real test double, not a mock: it actually executes its scripted
shell commands inside the repo, so the repo state and the events it returns are
consistent with each other and with what a checker will read. That is what makes
the end-to-end runner test trustworthy without a model call.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .schema import Usage

Event = dict  # {"type": "command", "command": str} | {"type": "message", "text": str} | {"type": "read", "path": str}


@dataclass(frozen=True)
class AgentRun:
    """One agent invocation, reduced to what the runner needs.

    `error` is the field that keeps a broken run from being scored as a rule miss.
    A rate-limited, timed-out or empty call produces no trajectory, and a checker
    reading that empty trajectory would happily report "no destructive command was
    run" as a pass. That is silent garbage wearing a result's clothes, so the runner
    records the cell as errored and leaves it to be retried instead of scoring it.
    """

    events: list[Event] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    error: str | None = None
    # Set by adapters whose host keeps a resumable transcript. It is what lets a long
    # session be recorded once and reused as seeded history by `recording.py`, instead
    # of every cell re-driving the same padding turns at one call each. An adapter
    # with no such concept leaves it None and nothing downstream changes.
    session_id: str | None = None


class Agent(Protocol):
    def run(self, turns: list[str], repo_dir: Path,
            env: dict[str, str] | None = None) -> AgentRun:
        ...


@dataclass
class FakeAgent:
    """A scripted agent. Runs each command in `commands` inside the repo (real side
    effects), records a command event per command, optionally a read event per path,
    and a final assistant message. Non-zero command exits are recorded, not raised:
    a real agent's failed command is part of its trajectory.

    It honours `env` when running its commands, so a test can prove the enforcement
    gate really blocks one without needing a live agent.
    """

    commands: list[str] = field(default_factory=list)
    final_text: str = ""
    reads: list[str] = field(default_factory=list)
    emit_command_events: bool = True
    usage: Usage = field(default_factory=Usage)

    def run(self, turns: list[str], repo_dir: Path,
            env: dict[str, str] | None = None) -> AgentRun:
        events: list[Event] = []
        for path in self.reads:
            events.append({"type": "read", "path": path})
        for cmd in self.commands:
            subprocess.run(cmd, cwd=repo_dir, shell=True, capture_output=True,
                           text=True, env=env)
            # A CLI that exposes no structured tool events is simulated by turning
            # this off: the command still really runs, so the shim becomes the only
            # way to observe it. That is the agy case the shim exists for.
            if self.emit_command_events:
                events.append({"type": "command", "command": cmd})
        events.append({"type": "message", "text": self.final_text})
        return AgentRun(events=events, usage=self.usage)
