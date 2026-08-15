#!/usr/bin/env python3
"""Render a bead as the task statement a run is given, from named fields only.

Whitelisted rather than filtered, and the difference is the whole point. A bead whose work has
already landed is the normal case for a benchmark task - the base tree is cut from before it, and
the finished commit is what proves the task solvable - so the tracker's record of that landing
travels with the bead. The first bead prepared this way carried, in its comment log:

    [2026-08-14 17:56 UTC] gabriel: Completed by <agent>. Implemented Reserve, PendingLease, and
    ReservationOutcome in …

which names the identifiers the canonical verification demands and announces that the work is done.
A run handed that is not solving anything. Filtering lines would have removed this one; whitelisting
fields makes the whole class unreachable, including the next field somebody adds to the tracker.

Reads `br show <id> --json` on stdin.
"""

import json
import sys

KEPT = ("id", "title", "issue_type", "priority", "labels", "description", "acceptance_criteria")


def render(bead: dict) -> str:
    lines = [f"{bead['id']} · {bead['title']}"]
    lines.append(f"Type: {bead.get('issue_type')} · Priority: P{bead.get('priority')}")
    labels = bead.get("labels") or []
    if labels:
        lines.append("Labels: " + ", ".join(labels))
    lines.append("")
    lines.append((bead.get("description") or "").rstrip())
    criteria = bead.get("acceptance_criteria")
    if criteria:
        lines += ["", "## Acceptance Criteria", "", criteria.rstrip()]
    return "\n".join(lines)


def main() -> int:
    bead = json.load(sys.stdin)
    if isinstance(bead, list):
        bead = bead[0]
    print(render(bead))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
