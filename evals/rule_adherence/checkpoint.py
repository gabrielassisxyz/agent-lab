"""Per-cell durability: write every result the moment it exists, and resume from
what is already on disk.

The first full run wrote nothing until all 90 cells had finished. That makes two
failure modes inevitable on a grid large enough to matter. A run that dies partway
(a spend limit, a kill, a machine reboot) loses everything it already paid for. And
a run that keeps going while its calls start failing writes a document that is part
result and part silence, which is worse than losing it, because it looks like data.

So: one append-only JSONL line per finished cell, one trace file per cell, and a
resume that skips what is already recorded. A kill costs at most the cell in flight.
Aggregation reads the checkpoint, so a run that never finished can still be scored
for the part it did.

Errored cells are recorded but **not** counted as done, so a resume retries them.
That is the difference between "we know this cell failed to run" and "this cell
found no violation", which a checker cannot tell apart on its own.
"""

from __future__ import annotations

import json
from pathlib import Path

from .placements import Axes
from .runner import RunOutcome
from .schema import CheckOutcome, Usage

CELLS_FILE = "cells.jsonl"
TRACES_DIR = "traces"


def cell_key(task_id: str, placement: str, axes: Axes, rep: int) -> str:
    """The identity of a cell. Every axis is in it, so widening the grid later cannot
    silently collide with results recorded under a narrower one.
    """
    return f"{task_id}|{placement}|{axes.label()}|r{rep}"


def key_of(outcome: RunOutcome) -> str:
    return cell_key(outcome.task_id, outcome.placement, outcome.axes, outcome.rep)


class Checkpoint:
    """An append-only record of finished cells under `out_dir`."""

    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.cells_path = self.out_dir / CELLS_FILE
        self.traces_dir = self.out_dir / TRACES_DIR

    def completed(self) -> set[str]:
        """Keys of cells that produced a real verdict. Errored cells are excluded on
        purpose: they are work still to do, not work already done.
        """
        done: set[str] = set()
        for record in self._records():
            if record.get("error") is None:
                done.add(record["key"])
            else:
                done.discard(record["key"])
        return done

    def record(self, outcome: RunOutcome) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        with self.cells_path.open("a") as handle:
            handle.write(json.dumps(_as_record(outcome)) + "\n")
        if outcome.trace:
            self.traces_dir.mkdir(parents=True, exist_ok=True)
            path = self.traces_dir / (key_of(outcome).replace("|", "__") + ".json")
            path.write_text(json.dumps(outcome.trace, indent=2) + "\n")

    def outcomes(self) -> list[RunOutcome]:
        """Rebuild the outcomes recorded so far, latest verdict per cell.

        A retried cell appears more than once; the last line wins, which is what makes
        a resume that re-ran an errored cell produce one clean result rather than two.
        """
        latest: dict[str, dict] = {}
        for record in self._records():
            latest[record["key"]] = record
        return [_from_record(r) for r in latest.values()]

    def _records(self) -> list[dict]:
        if not self.cells_path.exists():
            return []
        records = []
        for line in self.cells_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # A line torn by a kill mid-write is skipped rather than fatal: the
                # cell it belonged to is simply not marked done, so it gets retried.
                continue
        return records


def _as_record(outcome: RunOutcome) -> dict:
    check = outcome.outcome
    return {
        "key": key_of(outcome),
        "task": outcome.task_id,
        "placement": outcome.placement,
        "rep": outcome.rep,
        "turns": outcome.axes.turns,
        "filler_tokens": outcome.axes.filler_tokens,
        "seed": outcome.axes.seed,
        "passed": None if check is None else check.passed,
        "failure_mode": None if check is None else check.failure_mode,
        "detail": "" if check is None else check.detail,
        "enforcement_applied": outcome.enforcement_applied,
        "usage": {
            "input_tokens": outcome.usage.input_tokens,
            "output_tokens": outcome.usage.output_tokens,
            "cache_read_tokens": outcome.usage.cache_read_tokens,
            "cache_write_tokens": outcome.usage.cache_write_tokens,
        },
        "error": outcome.error,
    }


def _from_record(record: dict) -> RunOutcome:
    raw = record.get("usage") or {}
    check = None if record.get("passed") is None else CheckOutcome(
        passed=bool(record["passed"]),
        failure_mode=record.get("failure_mode"),
        detail=record.get("detail", ""),
    )
    return RunOutcome(
        task_id=record["task"],
        placement=record["placement"],
        rep=int(record.get("rep", 0)),
        axes=Axes(turns=int(record.get("turns", 1)),
                  filler_tokens=int(record.get("filler_tokens", 0)),
                  seed=int(record.get("seed", 0))),
        outcome=check,
        enforcement_applied=bool(record.get("enforcement_applied", False)),
        usage=Usage(
            input_tokens=int(raw.get("input_tokens", 0)),
            output_tokens=int(raw.get("output_tokens", 0)),
            cache_read_tokens=int(raw.get("cache_read_tokens", 0)),
            cache_write_tokens=int(raw.get("cache_write_tokens", 0)),
        ),
        error=record.get("error"),
    )
