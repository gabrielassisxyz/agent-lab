"""Reduce a raw trajectory + the repo the agent left behind into an `AgentResult`.

Two pure halves, both testable without a live agent:
- `reduce_events` pulls the facts the agent's own actions carry: the commands it
  ran, the files it read, and its final message.
- `read_repo_state` reads the rest from git: the commits made since a base sha, the
  branch, and the patch. These are facts about the repo, not opinions about it.

The branch the cell *started* on is passed in rather than read back, because by the
time this runs the agent may have moved HEAD. Without it, "never branched" and
"branched under a bad name" are indistinguishable, which is the defect the Opus run
exposed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .agent import Event
from .schema import AgentResult, Usage


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


def current_branch(repo_dir: Path) -> str | None:
    return _git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD") or None


def list_branches(repo_dir: Path) -> list[str]:
    """Every branch in the repo, including any a linked worktree checked out.

    Reading refs rather than HEAD is what makes "did it branch?" answerable. An agent
    that runs `git worktree add ../elsewhere -b docs/x` has branched, correctly, but
    HEAD in this directory is still the branch it started on. The first baseline
    sweep scored seven such cells as "never branched" and produced a placement
    spread that was entirely this mistake.
    """
    out = _git(repo_dir, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return [line for line in out.splitlines() if line.strip()]


def read_repo_state(repo_dir: Path, base_sha: str) -> tuple[list[str], str | None, str]:
    """Return (commit_messages_since_base, branch, patch_since_base).

    Commits are read across every branch, not just the one HEAD points at, for the
    same reason: work done on a branch checked out in another worktree is still the
    agent's work.
    """
    log = _git(repo_dir, "log", "--format=%B%x00", "--all", f"^{base_sha}")
    commit_messages = [m.strip() for m in log.split("\x00") if m.strip()]
    patch = _git(repo_dir, "diff", base_sha)
    return commit_messages, current_branch(repo_dir), patch


def merge_commands(parsed: list[str], from_shim: list[str]) -> list[str]:
    """Combine what the adapter parsed with what the shim logged.

    An adapter that exposes tool calls and the shim both see the same git command,
    so a plain union would count it twice. But the shim also sees commands an
    unstructured CLI never reported, and the adapter sees non-git commands the shim
    never wraps. Keeping the parsed list and appending only shim lines not already
    represented preserves both without inflating the count.
    """
    merged = list(parsed)
    for command in from_shim:
        if not any(command in existing or existing in command for existing in merged):
            merged.append(command)
    return merged


def build_result(events: list[Event], repo_dir: Path, base_sha: str,
                 base_branch: str | None = None, usage: Usage | None = None,
                 shim_commands: list[str] | None = None,
                 base_branches: list[str] | None = None) -> AgentResult:
    commands, reads, final_text = reduce_events(events)
    commit_messages, branch, patch = read_repo_state(repo_dir, base_sha)
    before = set(base_branches or [])
    created = [b for b in list_branches(repo_dir) if b not in before]
    return AgentResult(
        final_text=final_text,
        commands=merge_commands(commands, shim_commands or []),
        commit_messages=commit_messages,
        branch=branch,
        base_branch=base_branch,
        branches_created=created,
        files_read=reads,
        patch=patch,
        usage=usage or Usage(),
    )
