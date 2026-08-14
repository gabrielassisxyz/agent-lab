#!/usr/bin/env python3
"""Reduce one bead-cost run to the record the decision needs, from raw artefacts only.

Reads the agent's own session log rather than any summary it printed, for the reason the whole
experiment exists: a summary is the agent's claim about what it did, and the session log is what it
did. It is also the same source kernl's ledger reads for this dialect, so a figure here and a figure
there are the same measurement rather than two.

Deliberately reports what is ABSENT as absent. A missing token count is `null`, never zero - a zero
that means "unpriced" and a zero that means "free" are indistinguishable once written down, and the
one lane in this experiment whose cost is unpriced is exactly the one being piloted.

    ./collect.py <run-dir> [--session-dir DIR] [--worktree DIR]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys


def read_pi_session(session_dir: pathlib.Path) -> dict:
    """Sum per-turn usage across a pi session log.

    pi writes one JSON object per line; the shape varies by event, so this looks for a `usage`
    block wherever it appears rather than assuming a schema it has not verified.
    """
    logs = sorted(session_dir.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not logs:
        return {"session_log": None, "turns": None, "input_tokens": None, "output_tokens": None}

    log = logs[-1]
    totals = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "reasoning_tokens": 0}
    seen_usage = False
    turns = 0

    for line in log.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        usage = event.get("usage")
        if usage is None and isinstance(event.get("message"), dict):
            usage = event["message"].get("usage")
        if isinstance(usage, dict):
            seen_usage = True
            turns += 1
            for key, aliases in (
                ("input_tokens", ("input_tokens", "inputTokens", "prompt_tokens")),
                ("output_tokens", ("output_tokens", "outputTokens", "completion_tokens")),
                ("cache_read_tokens", ("cache_read_tokens", "cacheReadTokens", "cache_read_input_tokens")),
                ("reasoning_tokens", ("reasoning_tokens", "reasoningTokens")),
            ):
                for alias in aliases:
                    value = usage.get(alias)
                    if isinstance(value, (int, float)):
                        totals[key] += int(value)
                        break

    record = {"session_log": str(log), "turns": turns or None}
    record.update({key: (value if seen_usage else None) for key, value in totals.items()})
    return record


def read_worktree(worktree: pathlib.Path) -> dict:
    """What the run left behind: whether it committed, and how large the change was."""

    def git(*args: str) -> str | None:
        result = subprocess.run(
            ["git", "-C", str(worktree), *args], capture_output=True, text=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    base = git("merge-base", "HEAD", "origin/main") or git("rev-parse", "HEAD~1")
    head = git("rev-parse", "HEAD")
    committed = bool(base and head and base != head)

    stat = git("diff", "--numstat", base, "HEAD") if committed else git("diff", "--numstat")
    added = removed = files = 0
    for row in (stat or "").splitlines():
        parts = row.split("\t")
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            added += int(parts[0])
            removed += int(parts[1])
            files += 1

    return {
        "committed": committed,
        "head": head,
        "diff_files": files or None,
        "diff_added": added or None,
        "diff_removed": removed or None,
        "dirty": bool(git("status", "--porcelain")),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=pathlib.Path)
    parser.add_argument("--session-dir", type=pathlib.Path)
    parser.add_argument("--worktree", type=pathlib.Path)
    args = parser.parse_args()

    record: dict = {"run": args.run_dir.name}

    for name in ("started_at", "ended_at", "exit_code"):
        path = args.run_dir / name
        record[name] = path.read_text().strip() if path.exists() else None

    # The wall clock is recorded and immediately qualified. It includes time spent waiting on
    # upstream rate limits, so it measures the queue alongside the agent and is never a clean
    # signal on its own.
    record["wall_time_note"] = "includes upstream backoff; not a clean signal"
    # A run killed by its own timeout is a failed run, not a model that got the answer wrong. The
    # two cost the same quota and mean opposite things.
    record["timeout"] = record.get("exit_code") in ("exit: 124", "124")

    session_dir = args.session_dir or (args.run_dir / "home" / ".pi" / "agent" / "sessions")
    record["usage"] = read_pi_session(session_dir) if session_dir.exists() else None
    record["worktree"] = read_worktree(args.worktree) if args.worktree else None

    json.dump(record, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
