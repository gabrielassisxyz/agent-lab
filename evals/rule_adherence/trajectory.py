"""Reduce a raw trajectory + the repo the agent left behind into an `AgentResult`
(Phase 1).

Two pure halves, both testable without a live agent:
- `reduce_events` pulls the facts the agent's own actions carry: the commands it
  ran, the files it read, and its final message.
- `read_repo_state` reads the rest from git: the commits made since a base sha, the
  branch, and the patch. These are facts about the repo, not opinions about it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .agent import Event
from .schema import AgentResult


def reduce_events(events: list[Event]) -> tuple[list[str], list[str], str]:
    """Return (commands, files_read, final_text) from the event stream."""
    commands = [e["command"] for e in events if e.get("type") == "command"]
    reads = [e["path"] for e in events if e.get("type") == "read"]
    messages = [e["text"] for e in events if e.get("type") == "message"]
    final_text = messages[-1] if messages else ""
    return commands, reads, final_text


def _git(repo_dir: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo_dir, capture_output=True, text=True)
    return out.stdout.strip()


def read_repo_state(repo_dir: Path, base_sha: str) -> tuple[list[str], str | None, str]:
    """Return (commit_messages_since_base, branch, patch_since_base)."""
    log = _git(repo_dir, "log", "--format=%B%x00", f"{base_sha}..HEAD")
    commit_messages = [m.strip() for m in log.split("\x00") if m.strip()]
    branch = _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD") or None
    patch = _git(repo_dir, "diff", base_sha)
    return commit_messages, branch, patch


def build_result(events: list[Event], repo_dir: Path, base_sha: str) -> AgentResult:
    commands, reads, final_text = reduce_events(events)
    commit_messages, branch, patch = read_repo_state(repo_dir, base_sha)
    return AgentResult(
        final_text=final_text,
        commands=commands,
        commit_messages=commit_messages,
        branch=branch,
        files_read=reads,
        patch=patch,
    )
