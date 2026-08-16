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
import shutil
import sqlite3
import subprocess
import sys
import tempfile


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
            # The bare forms - `input`, `output`, `cacheRead`, `reasoning` - are the ones pi
            # actually writes, and they were missing from every list below. The result was not a
            # crash but the worst possible output: a well-formed record reporting 0 tokens for a
            # run of 22 turns, which reads as a measurement and is not one.
            for key, aliases in (
                ("input_tokens", ("input", "input_tokens", "inputTokens", "prompt_tokens")),
                ("output_tokens", ("output", "output_tokens", "outputTokens", "completion_tokens")),
                ("cache_read_tokens", ("cacheRead", "cache_read_tokens", "cacheReadTokens", "cache_read_input_tokens")),
                ("reasoning_tokens", ("reasoning", "reasoning_tokens", "reasoningTokens")),
            ):
                for alias in aliases:
                    value = usage.get(alias)
                    if isinstance(value, (int, float)):
                        totals[key] += int(value)
                        break

    record = {"session_log": str(log), "turns": turns or None}
    record.update({key: (value if seen_usage else None) for key, value in totals.items()})
    # Ollama does not publish cache information at all, so pi's `cacheRead` is a field with a
    # default rather than a reading. Summed it comes out as a confident 0, and a 0 that means "not
    # reported" priced against a 0 that means "no cache was read" is a cost conclusion drawn from
    # nothing. Said here rather than left for whoever reads the table.
    record["cache_read_note"] = "the Ollama lanes do not report cache reads; a 0 here is absence, not a measurement"
    # Summing per-turn input counts the whole prompt again every turn, which is what the lane
    # actually sends but NOT what the other lane's envelope reports. The two are not comparable.
    record["input_note"] = "per-turn input summed; not comparable with an envelope-reported total"
    return record


def read_json_envelope(stdout: pathlib.Path) -> dict | None:
    """Pull the one JSON object a harness writes to stdout, tolerating anything printed around it.

    WHY tolerantly, rather than parsing the whole file. Both envelope harnesses write one object and
    nothing else - until something upstream writes a line first. `mise` announces the tool version it
    activated (`mise … tools: claude@2.1.233`) whenever it has to activate one, which depends on what
    the jail's cache already holds and on nothing this experiment controls. One claude run carried
    that line and an earlier one did not, and the strict reader returned None for the run that did.

    That failure is the dangerous shape rather than a loud one: the record comes out well formed with
    `usage: null`, which reads as a harness that reports no usage rather than as a parser that gave
    up. Left alone it would have emptied a whole arm of its token and cost columns while every run in
    it passed its verdict, and the tables would have agreed with each other about it.
    """
    if not stdout.exists():
        return None
    text = stdout.read_text(errors="replace")
    candidates = [text]
    # From the first brace, for an envelope preceded by noise; then each line that could be an
    # object on its own, newest first, for a harness that prints after it as well as before.
    brace = text.find("{")
    if brace > 0:
        candidates.append(text[brace:])
    candidates.extend(line for line in reversed(text.splitlines()) if line.startswith("{"))
    for candidate in candidates:
        try:
            envelope = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(envelope, dict):
            return envelope
    return None


AGY_MODEL_STEP = 15


def count_agy_steps(run_home: pathlib.Path) -> int | None:
    """Count the model's turns in agy's trajectory database.

    The envelope's `num_turns` counts agy's own retries and reports 1 for a run of any length, which
    leaves the metric with the most headroom in this experiment missing for a whole arm. The real
    count is in the SQLite trajectory the CLI keeps beside its conversation.

    `step_type = 15` is the model step. That is not a guess: an earlier round recorded 132 turns for
    a run by reading this database, and this query returns exactly 132 for that run's trajectory.
    Opened read-only through a copy, because the live database is journalled and a run may still be
    writing to it.
    """
    conversations = run_home / ".gemini" / "antigravity-cli" / "conversations"
    dbs = sorted(conversations.glob("*.db"), key=lambda p: p.stat().st_mtime) if conversations.is_dir() else []
    if not dbs:
        return None
    live = dbs[-1]
    with tempfile.TemporaryDirectory() as scratch:
        copy = pathlib.Path(scratch) / "c.db"
        shutil.copy2(live, copy)
        wal = live.with_name(live.name + "-wal")
        if wal.exists():
            shutil.copy2(wal, copy.with_name("c.db-wal"))
        try:
            con = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
            return con.execute("select count(*) from steps where step_type = ?",
                               (AGY_MODEL_STEP,)).fetchone()[0]
        except sqlite3.Error:
            return None


def read_agy_envelope(stdout: pathlib.Path, run_home: pathlib.Path | None = None) -> dict | None:
    """Read the single JSON envelope agy writes at the end of a `--print` run.

    agy does not stream: launched with `--output-format=json` it emits one object when the run is
    over, so there is no per-turn log to sum and the envelope IS the measurement for tokens.

    Turns are the exception and come from the trajectory database instead. The envelope's
    `num_turns` counts agy's own retries: five runs of this lane reported 1 apiece while doing
    between 48 and 79 model steps, and a column that is constant across a dimension it should vary
    on is the signature this repo has learned to hunt. The envelope's own figure is kept under a
    name that says what it counts rather than being silently replaced.

    The lanes' figures are NOT comparable and must never be quoted as if they were: agy reports
    cache reads and the Ollama lanes do not report them at all, so summing per-turn input on one
    side and reading an envelope on the other counts different things.
    """
    envelope = read_json_envelope(stdout)
    if envelope is None or not isinstance(envelope.get("usage"), dict):
        return None

    usage = envelope["usage"]
    steps = count_agy_steps(run_home) if run_home else None
    record = {
        "session_log": str(stdout),
        "status": envelope.get("status"),
        "turns": steps if steps is not None else envelope.get("num_turns"),
        "turns_source": "trajectory database, step_type 15" if steps is not None
                        else "envelope num_turns; counts agy's own retries, not model turns",
        "envelope_num_turns": envelope.get("num_turns"),
        "duration_seconds": envelope.get("duration_seconds"),
    }
    for key, aliases in (
        ("input_tokens", ("input_tokens",)),
        ("output_tokens", ("output_tokens",)),
        ("cache_read_tokens", ("cache_read_tokens",)),
        ("reasoning_tokens", ("thinking_tokens", "reasoning_tokens")),
    ):
        record[key] = next(
            (usage[alias] for alias in aliases if isinstance(usage.get(alias), (int, float))), None
        )
    return record


def read_claude_envelope(stdout: pathlib.Path) -> dict | None:
    """Read the JSON envelope Claude Code writes at the end of a `-p --output-format json` run.

    Like agy and unlike pi, the envelope IS the measurement: one object at the end, no per-turn log
    to sum, so `input_tokens` here is the real billed input and not the same quantity as the pi
    lane's per-turn sum. The three lanes' token columns must never be put side by side.

    Two fields need naming rather than copying. `total_cost_usd` is a LIST PRICE the harness did not
    pay - this lane authenticates with a subscription account's token, so the money number describes
    what the same traffic would have cost on the API and describes nothing about this run's bill. It
    is carried under a name that says so. And cache creation is reported separately from cache
    reads, which no other lane here distinguishes, so it is kept under its own key instead of being
    folded into one of theirs.
    """
    envelope = read_json_envelope(stdout)
    if envelope is None or not isinstance(envelope.get("usage"), dict):
        return None
    # `modelUsage` is what separates this envelope from agy's, which also carries a `usage` dict.
    model_usage = envelope.get("modelUsage")
    if not isinstance(model_usage, dict):
        return None

    usage = envelope["usage"]
    details = usage.get("output_tokens_details")
    thinking = details.get("thinking_tokens") if isinstance(details, dict) else None
    return {
        "session_log": str(stdout),
        "status": envelope.get("subtype"),
        "stop_reason": envelope.get("stop_reason"),
        "terminal_reason": envelope.get("terminal_reason"),
        "turns": envelope.get("num_turns"),
        "answered_by": sorted(model_usage),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cache_read_tokens": usage.get("cache_read_input_tokens"),
        "cache_write_tokens": usage.get("cache_creation_input_tokens"),
        "reasoning_tokens": thinking,
        "list_price_usd_not_paid": envelope.get("total_cost_usd"),
        "list_price_note": (
            "list price for the same traffic on the API; this lane runs on a subscription token and "
            "was not billed this"
        ),
        "input_note": "billed input reported by the harness; not comparable with pi's per-turn sum",
    }


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

    # `git diff` does not see a file git has never been told about, and a run that solves the bead
    # in a NEW file and never commits leaves all of its work in exactly that blind spot. One run
    # wrote 137 lines into a new file, was graded 16/16 on them, and was recorded here as a
    # thirteen-line change - so the size of a solution read as an outlier of the model rather than
    # as a hole in the measurement. Untracked files are counted as pure additions, which is what
    # they are.
    untracked = (git("ls-files", "--others", "--exclude-standard") or "").splitlines()
    for name in untracked:
        path = worktree / name
        try:
            added += len(path.read_text(errors="replace").splitlines())
        except OSError:
            continue
        files += 1

    return {
        "committed": committed,
        "head": head,
        "diff_files": files or None,
        "diff_added": added or None,
        "diff_removed": removed or None,
        # True means the run left changes outside its commit, including work in files git was never
        # told about. It stopped meaning "the scorer wrote a fixture in here" when the scorer moved
        # to grading a disposable copy.
        "dirty": bool(git("status", "--porcelain")),
        "untracked_files": len(untracked) or None,
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

    # `harness` and `model` are recorded separately because a lane is the PAIR of them, and the two
    # halves answer different questions: the same model through two harnesses is not one measurement
    # (one reports an envelope total, the other a per-turn sum), and the same harness on two models
    # is the comparison this experiment exists to make. The marker file keeps its historical name
    # `lane`; dozens of run directories on disk carry it and re-collection from kept artefacts has to
    # keep working, which is the whole reason the artefacts are kept.
    harness_file = args.run_dir / "lane"
    record["harness"] = harness_file.read_text().strip() if harness_file.exists() else None
    model_file = args.run_dir / "model"
    record["model"] = model_file.read_text().strip() if model_file.exists() else None

    # Each harness keeps its usage somewhere different, so the source is chosen rather than guessed:
    # pi streams a session log, agy writes one envelope at the end. Trying the pi log first and
    # falling through keeps a run whose harness was never recorded readable.
    # The claude harness is dispatched by name rather than left to the fallthrough: its envelope also
    # carries a `usage` dict, so agy's reader would parse it and return a record that is wrong in
    # the fields it happens to share and silently empty in the rest.
    if record["harness"] == "claude":
        usage = read_claude_envelope(args.run_dir / "stdout.txt")
    else:
        session_dir = args.session_dir or (args.run_dir / "home" / ".pi" / "agent" / "sessions")
        usage = read_pi_session(session_dir) if session_dir.exists() else None
        if usage is None or usage.get("turns") is None:
            usage = read_agy_envelope(args.run_dir / "stdout.txt", args.run_dir / "home") or usage
    record["usage"] = usage
    record["worktree"] = read_worktree(args.worktree) if args.worktree else None

    json.dump(record, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
