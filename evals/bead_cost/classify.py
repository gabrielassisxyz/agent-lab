#!/usr/bin/env python3
"""Say what one run's outcome actually was, in the vocabulary the arithmetic needs.

The scorer grades whatever tree it is handed, so an untouched base tree returns the same verdict a
wrong fix does. Those two mean opposite things: one lane produced an answer that is wrong, and the
other produced no answer at all. A third case looks like both and is neither, because the lane was
never reachable. Collapsing them into "failed" is how a lane gets written down as incapable of a
task it was never given.

    ./classify.py <run-dir>        prints one word

    admitted     the canonical verification passed on every criterion
    wrong        the run left a diff and the verification rejected it
    no-diff      the run finished and left the tree at its base commit
    aborted      the lane errored out mid-edit and the tree was never scored
    unreachable  the lane could not be reached: rate limit, quota, credentials, unknown model
    truncated    the model's last turn hit its output ceiling and the session ended
    broken       the run never got far enough to produce any of the above
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

UNREACHABLE = re.compile(
    r"429|rate.?limit|quota|authentication failed|not logged in|no such model|model .* not found",
    re.IGNORECASE,
)


def read_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def last_stop_reason(record: dict | None) -> str | None:
    """The stop reason of the final turn, read from the harness's own log.

    Truncation is invisible in every other artifact: the run exits zero, stdout is empty and the
    tree is untouched, which is indistinguishable from a model that simply declined to act.
    """
    if not record:
        return None
    usage = record.get("usage") or {}
    log = usage.get("session_log")
    if not log or not log.endswith(".jsonl"):
        return None
    stop = None
    try:
        for line in pathlib.Path(log).read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = event.get("message") if isinstance(event, dict) else None
            if isinstance(message, dict) and message.get("stopReason"):
                stop = message["stopReason"]
    except OSError:
        return None
    return stop


def classify(run_dir: pathlib.Path) -> str:
    verdict = read_json(run_dir / "verdict.json")
    record = read_json(run_dir / "record.json")

    # What the run PRODUCED is decided before why it might not have, and the order is a correction.
    # Reachability used to be checked first, against the raw streams, which reads any mention of a
    # rate limit as the lane being unusable. A run of 474 turns over 68 minutes that survived a
    # transient 429, committed a fix and scored five of five was classified `unreachable` on that
    # basis, and cost its lane a rest round. A run that produced work was reachable, whatever its
    # logs mention along the way.
    if verdict and verdict.get("scored"):
        section = verdict.get("section_a") or {}
        if section and all(section.values()):
            return "admitted"

    worktree = (record or {}).get("worktree") or {}
    if worktree.get("committed") or worktree.get("dirty"):
        # An edit left behind by a lane that died is not an answer, and `wrong` is the expensive
        # place to put it: cost per completed bead divides by the runs that completed, so a lane
        # failure in the denominator is charged to the model as if it had produced a rejected fix.
        # The distinction is not visible in the tree, which looks the same either way - it is the
        # absence of a verdict beside a harness that reported its own error.
        if not (verdict or {}).get("scored") and ((record or {}).get("usage") or {}).get("status") == "ERROR":
            return "aborted"
        return "wrong"

    # Only now, with nothing produced, does the reason matter.
    blob = ""
    for name in ("stderr.txt", "stdout.txt"):
        try:
            blob += (run_dir / name).read_text(errors="replace")
        except OSError:
            pass
    if UNREACHABLE.search(blob):
        return "unreachable"

    if record is not None:
        if last_stop_reason(record) == "length":
            return "truncated"
        if (record.get("usage") or {}).get("status") == "ERROR":
            return "unreachable"
        return "no-diff"

    return "broken"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    print(classify(pathlib.Path(sys.argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
