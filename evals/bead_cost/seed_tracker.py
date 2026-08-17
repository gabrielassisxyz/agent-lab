#!/usr/bin/env python3
"""Give a run's checkout a tracker holding ONE bead, built from the fields the prompt already shows.

WHY THIS EXISTS. The subject's `.beads` is a symlink to `local/`, which is git-ignored, so a
checkout cut from the base repository has a tracker that points at nothing. In a real session that
directory resolves; in a run it does not, and the subject's own AGENTS.md says, in as many words,
that when a coordination protection is unavailable an agent must not implement or commit until it
is restored.

That is not a hypothetical cost. Measured on three runs of one harness against this bead: two read
the rule, obeyed it, and stopped before editing anything; the third implemented and passed 16 of 16.
Same prompt, same environment, a coin flip - and every other lane in the campaign scored by ignoring
an explicit instruction in the repository it was working in. An instrument that rewards that is
measuring the opposite of what it claims to.

WHY IT CANNOT LEAK THE ANSWER. The record is built from `bead_prompt.KEPT` - the same whitelist that
renders the task statement - so what the tracker can tell an agent is a subset of what its prompt
already said. That is by construction rather than by inspection, and the import is refused if a
field outside the list ever reaches the record. The bead's `comments` are the specific hazard: on
this subject the log reads "Completed by <agent>. Implemented Reserve, PendingLease, and
ReservationOutcome in ...", which names the identifiers the canonical verification demands.

    ./seed_tracker.py <checkout> --subject <path> --bead <id>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from bead_prompt import KEPT  # noqa: E402

# Everything the tracker needs that is not part of the task statement. Kept apart from KEPT rather
# than added to it, so the whitelist that governs what an agent can READ stays exactly the
# whitelist the prompt uses.
STRUCTURAL = ("created_at", "updated_at")

# The fields that say the work is already done. They are named here rather than trusted to stay out,
# because the whitelist this file borrows lives in another file and is one edit away from growing:
# `comments` reads like useful context for a task statement right up until you notice that on this
# bead it says which functions to write. A deny-list beside a whitelist is not redundant when the
# whitelist is somebody else's.
NEVER = ("comments", "close_reason", "closed_at", "resolution", "resolution_notes")


def build_record(bead: dict) -> dict:
    """One JSONL record: the prompt's fields, plus the timestamps, and open.

    OPEN, not the status the bead actually carries. This bead is closed - its work landed, which is
    what proves the task solvable - and a tracker that says so hands the run the answer to the only
    question it was asked. The run's task is to do this work, so in the run's tracker it is work to
    be done. Nothing else about the record is changed.
    """
    record = {key: bead[key] for key in KEPT if bead.get(key) is not None}
    if "id" not in record or "title" not in record:
        raise ValueError("the bead has no id or no title; refusing to seed a tracker from it")
    for key in STRUCTURAL:
        if bead.get(key) is not None:
            record[key] = bead[key]
    record["status"] = "open"

    leaked = sorted(set(record) & set(NEVER))
    if leaked:
        raise ValueError(f"refusing to seed a tracker carrying a completion record: {leaked}. "
                         f"Whatever added these to the whitelist also put them in the prompt.")
    return record


def read_bead(subject: pathlib.Path, bead_id: str) -> dict:
    result = subprocess.run(["br", "show", bead_id, "--json"], cwd=str(subject),
                            capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit(f"seed-tracker: `br show {bead_id}` failed in {subject}:\n{result.stderr}")
    bead = json.loads(result.stdout)
    return bead[0] if isinstance(bead, list) else bead


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout", type=pathlib.Path)
    ap.add_argument("--subject", type=pathlib.Path, required=True)
    ap.add_argument("--bead", required=True)
    ap.add_argument("--prefix", default="", help="issue id prefix; derived from the bead id if unset")
    ap.add_argument("--dir", default="local/_beads",
                    help="where the subject's .beads symlink points, relative to the checkout")
    args = ap.parse_args()

    beads_dir = args.checkout / args.dir
    database = beads_dir / "beads.db"
    if database.exists():
        print(f"seed-tracker: {database} already exists; leaving it alone")
        return 0

    record = build_record(read_bead(args.subject, args.bead))
    beads_dir.mkdir(parents=True, exist_ok=True)
    (beads_dir / "issues.jsonl").write_text(json.dumps(record) + "\n")

    prefix = args.prefix or args.bead.split("-", 1)[0]
    for command in (["br", "init", "--prefix", prefix, "--db", str(database)],
                    ["br", "sync", "--import-only", "--db", str(database)]):
        result = subprocess.run(command, cwd=str(args.checkout), capture_output=True, text=True)
        if result.returncode != 0:
            raise SystemExit(f"seed-tracker: {' '.join(command)} failed:\n"
                             f"{result.stdout}{result.stderr}")

    # Asked of the tracker rather than of the file that was written, because what matters is what an
    # agent reading it will see - and `br` is what the agent will ask.
    check = subprocess.run(["br", "show", args.bead, "--json", "--db", str(database)],
                           cwd=str(args.checkout), capture_output=True, text=True)
    seeded = json.loads(check.stdout) if check.stdout.strip() else {}
    if isinstance(seeded, list):
        seeded = seeded[0] if seeded else {}
    if seeded.get("id") != args.bead:
        raise SystemExit("seed-tracker: the seeded tracker does not hold the bead it was given")
    if seeded.get("comments") or seeded.get("close_reason") or seeded.get("closed_at"):
        raise SystemExit("seed-tracker: the seeded bead carries a completion record - refusing, "
                         "that is the leak this script exists to make impossible")

    print(f"seed-tracker: {args.bead} seeded into {beads_dir} (1 issue, open, no comments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
