#!/usr/bin/env python3
"""Reduce every run under the bead-cost root to one table, from the artefacts on disk.

Regenerated rather than maintained. A night of runs is dozens of records, and a hand-kept summary
drifts from the artefacts the moment one run is re-scored - which happens, because re-scoring from
kept artefacts is how a metric gets repaired without paying for the runs again.

    ./tabulate.py [--root DIR] [--json]

Cost per completed bead is deliberately NOT computed here. The arithmetic divides the cost of every
run by the runs that completed, and the two lanes' token counts are not comparable: one harness
reports an envelope total and the other a per-turn sum, and one meter reports cache reads while the
other does not report them at all. Printing a single number over those would be inventing one.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from classify import classify  # noqa: E402

# Every build on this machine inside this window linked a `spider` patched by a run, which already
# fixed the subject bead. Runs developed inside it committed work that reduces to the untouched base
# when rebuilt against a pristine crate, so their verdicts say nothing about the model.
POISONED = (
    dt.datetime.fromisoformat("2026-08-15T00:22:00-03:00"),
    dt.datetime.fromisoformat("2026-08-15T01:00:00-03:00"),
)


def load(path: pathlib.Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def when(run_dir: pathlib.Path, name: str):
    try:
        return dt.datetime.fromisoformat((run_dir / name).read_text().strip())
    except (OSError, ValueError):
        return None


def row(run_dir: pathlib.Path) -> dict:
    record = load(run_dir / "record.json") or {}
    verdict = load(run_dir / "verdict.json") or {}
    usage = record.get("usage") or {}
    worktree = record.get("worktree") or {}
    started, ended = when(run_dir, "started_at"), when(run_dir, "ended_at")

    section = verdict.get("section_a") or {}
    passed = sum(1 for value in section.values() if value) if section else None

    poisoned = bool(started and POISONED[0] <= started <= POISONED[1])

    return {
        "run": run_dir.name,
        "lane": record.get("lane"),
        "model": record.get("model"),
        "base": (run_dir / "base_commit").read_text().strip()[:7]
        if (run_dir / "base_commit").exists()
        else None,
        "outcome": "poisoned-window" if poisoned else classify(run_dir),
        # Blanked for a poisoned run rather than shown. The verdict on disk for those is a real
        # number produced by a real build against a dependency that already fixed the subject, so
        # printing it beside the warning invites exactly the reading the warning exists to prevent.
        "section_a": None if poisoned else (f"{passed}/5" if passed is not None else None),
        "committed": worktree.get("committed"),
        "files": worktree.get("diff_files"),
        "wall_s": int((ended - started).total_seconds()) if started and ended else None,
        "turns": usage.get("turns"),
        "input": usage.get("input_tokens"),
        "output": usage.get("output_tokens"),
        "reasoning": usage.get("reasoning_tokens"),
        "cache_read": usage.get("cache_read_tokens"),
        "started": started.strftime("%m-%d %H:%M") if started else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.home() / "tmp/bead-cost")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = [
        row(child)
        for child in sorted(args.root.iterdir())
        if child.is_dir()
        and not child.name.startswith("_")
        and (child / "started_at").exists()
    ]
    rows.sort(key=lambda item: item["started"] or "")

    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        print()
        return 0

    columns = ["started", "run", "lane", "model", "outcome", "section_a", "committed", "wall_s", "turns", "input", "output"]
    widths = {c: max(len(c), *(len(str(r.get(c))) for r in rows)) if rows else len(c) for c in columns}
    print("  ".join(c.ljust(widths[c]) for c in columns))
    for item in rows:
        print("  ".join(str(item.get(c)).ljust(widths[c]) for c in columns))

    print()
    for lane in sorted({r["lane"] for r in rows if r["lane"]}):
        lane_rows = [r for r in rows if r["lane"] == lane]
        usable = [r for r in lane_rows if r["outcome"] not in ("poisoned-window", "broken")]
        admitted = [r for r in usable if r["outcome"] == "admitted"]
        print(f"{lane}: {len(lane_rows)} runs, {len(usable)} usable, {len(admitted)} admitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
