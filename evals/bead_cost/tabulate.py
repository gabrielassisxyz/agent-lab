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
import re
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
        # `lane` was the field's name until the harness and the lane were told apart, and records
        # collected before that carry the old key holding the same value. Read both, or every run
        # predating the rename prints a blank column and reads as a run whose harness went
        # unrecorded, which is a different and much more alarming thing.
        "harness": record.get("harness") or record.get("lane"),
        "model": record.get("model"),
        "base": (run_dir / "base_commit").read_text().strip()[:7]
        if (run_dir / "base_commit").exists()
        else None,
        "outcome": "poisoned-window" if poisoned else classify(run_dir),
        # Blanked for a poisoned run rather than shown. The verdict on disk for those is a real
        # number produced by a real build against a dependency that already fixed the subject, so
        # printing it beside the warning invites exactly the reading the warning exists to prevent.
        # The denominator comes from the verdict rather than from the first subject's five criteria.
        # Hard coded it printed `16/5` for every run of the Go bead, which is not a fabricated
        # number but is a wrong one, in the table the results pages tell people to regenerate.
        # Records written before the field existed fall back to the five they were graded against.
        "section_a": None if poisoned else (
            f"{passed}/{verdict.get('total', len(section) or 5)}" if passed is not None else None),
        # A tree that does not build is the shape of a near-miss on this subject, not an unscored
        # run, so the flag belongs beside the score rather than only inside the verdict file.
        "build_failed": verdict.get("build_failed"),
        # `section_a` above now answers "did it solve the bead" - the canonical file over the tree as
        # the run left it. This is the other half, and it has to be printed rather than kept in the
        # verdict: eight runs of this campaign solved the bead and broke the package's older tests
        # by removing a public method those tests call, and while the two answers were one number
        # every one of them read as having produced nothing. `None` is a verdict written before the
        # scorer reported two regimes, not a pass.
        "legacy_ok": verdict.get("pre_existing_tests_pass"),
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

    columns = ["started", "run", "harness", "model", "outcome", "section_a", "legacy_ok",
               "committed", "wall_s", "turns", "input", "output"]
    widths = {c: max(len(c), *(len(str(r.get(c))) for r in rows)) if rows else len(c) for c in columns}
    print("  ".join(c.ljust(widths[c]) for c in columns))
    for item in rows:
        print("  ".join(str(item.get(c)).ljust(widths[c]) for c in columns))

    print()
    # Grouped by model rather than by harness. Two of the three models under test run through the
    # same harness, so a per-harness tally silently averages a lane that is four for four with one
    # that is nought for four.
    # The `-kN` suffix pins which of three accounts served a run, so that a rate limit lands on one
    # ceiling rather than three. It is not the subject of the measurement, and leaving it in splits
    # one model into three tallies of one or two runs each.
    def subject(name: str) -> str:
        return re.sub(r"-k[0-9]+$", "", name)

    for model in sorted({subject(r["model"]) for r in rows if r["model"]}):
        model_rows = [r for r in rows if r["model"] and subject(r["model"]) == model]
        # `usable` means the run says something about the model. A poisoned window, a lane that
        # errored out mid-edit, a lane that was never reached and a run that never started all say
        # something about the machine instead, and each one of them in the denominator reads as a
        # model that failed. A model's OWN failure - a rejected fix - stays in, because someone has
        # to pay for it twice.
        #
        # `blocked` joins them, and it is the newest and least obvious member. Those runs declined
        # to edit because the subject's AGENTS.md forbids implementing while a coordination
        # protection is unavailable - and that protection is not running on this machine at all, so
        # a real session in that repository would meet the same wall. It is an environment gap, and
        # an environment gap belongs in neither the attempt count nor the token means: charging one
        # metric and not the other would be the same run counted two ways.
        #
        # It is not hidden by being excluded. The line below prints runs AND usable, so the gap
        # between them is the count of everything the machine cost, visible without entering a mean.
        instrument = ("poisoned-window", "broken", "aborted", "unreachable", "blocked")
        usable = [r for r in model_rows if r["outcome"] not in instrument]
        admitted = [r for r in usable if r["outcome"] == "admitted"]
        blocked = [r for r in model_rows if r["outcome"] == "blocked"]
        median_wall = sorted(r["wall_s"] for r in usable if r["wall_s"]) or [None]
        print(
            f"{model}: {len(model_rows)} runs, {len(usable)} usable, {len(admitted)} admitted"
            + (f", {len(blocked)} blocked by an unavailable protection" if blocked else "")
            + (f", median {median_wall[len(median_wall) // 2]}s" if median_wall[0] else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
