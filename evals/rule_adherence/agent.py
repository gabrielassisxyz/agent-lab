"""The agent adapter (Phase 1): the boundary between the runner and whatever produces
a trajectory.

An adapter takes a composed prompt and a staged repo and returns a list of events
(the shape a sandbox run writes to events.jsonl). The runner never knows which agent
it drove, which is what lets the same experiment compare Claude Code, pi, or a fake.

`FakeAgent` is a real test double, not a mock: it actually executes its scripted
shell commands inside the repo, so the repo state and the events it returns are
consistent with each other and with what a checker will read. That is what makes the
end-to-end runner test trustworthy without a model call. The real sandboxed CLI
adapter (drive `claude -p` / `pi`, parse its events.jsonl) is the next increment and
is deliberately not stubbed here.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


Event = dict  # {"type": "command", "command": str} | {"type": "message", "text": str} | {"type": "read", "path": str}


class Agent(Protocol):
    def run(self, prompt: str, repo_dir: Path) -> list[Event]:
        ...


@dataclass
class FakeAgent:
    """A scripted agent. Runs each command in `commands` inside the repo (real side
    effects), records a command event per command, optionally a read event per path,
    and a final assistant message. Non-zero command exits are recorded, not raised:
    a real agent's failed command is part of its trajectory.
    """

    commands: list[str] = field(default_factory=list)
    final_text: str = ""
    reads: list[str] = field(default_factory=list)

    def run(self, prompt: str, repo_dir: Path) -> list[Event]:
        events: list[Event] = []
        for path in self.reads:
            events.append({"type": "read", "path": path})
        for cmd in self.commands:
            subprocess.run(cmd, cwd=repo_dir, shell=True, capture_output=True, text=True)
            events.append({"type": "command", "command": cmd})
        events.append({"type": "message", "text": self.final_text})
        return events
