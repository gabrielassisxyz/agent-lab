#!/usr/bin/env python3
"""Render an agy run's trajectory, live or after the fact.

    ./agy_trail.py <run-home> --follow      # watch a run in progress
    ./agy_trail.py <run-home>               # read one that finished

The counterpart to `trail.py`, which follows a pi session. It exists separately because agy does
not stream: launched with `--output-format=json` it writes one envelope at the very end, so there
is no file to `tail -f`. Its live trajectory is a SQLite database under
`<home>/.gemini/antigravity-cli/conversations/`, and that is what this reads.

**It snapshots rather than reads in place, and drops the `-shm` when it does.** The writer holds
the database open with a large WAL, so a direct read returns an empty `sqlite_master` - the schema
itself is still in the WAL. Copying the `.db` and the `-wal` while deliberately leaving the `-shm`
behind forces SQLite to recover from the WAL and produces a consistent snapshot. Copying all three
does not: the shm tells SQLite no recovery is needed and it sees nothing. Measured against a live
run, all three ways.

Consequence worth stating: this is a **poll**, not a tail. Each cycle copies the database, so the
view is as fresh as the last cycle and no fresher.

The payload blobs are protobuf, and this deliberately does not parse them. Tool names and the
tool's own summary are embedded as readable text and that is all a person following a run needs;
a hand-rolled protobuf reader would be a second, undocumented schema to maintain against a CLI
that has already changed its flags underneath this project once.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import time

# Printable runs of four or more, which is what separates an embedded string from protobuf framing.
READABLE = re.compile(rb"[\x20-\x7e]{4,}")
# The tool call's own description of itself, which agy embeds as JSON beside the arguments.
ACTION = re.compile(r'"tool(?:Action|Summary)"\s*:\s*"([^"]{1,200})"')
# The identifier sitting immediately before the arguments object is the tool name.
TOOL_BEFORE_ARGS = re.compile(r'([a-z][a-z0-9_]{2,29})\s*\{"')


def snapshot(run_home: pathlib.Path, into: pathlib.Path) -> pathlib.Path | None:
    conversations = run_home / ".gemini" / "antigravity-cli" / "conversations"
    dbs = sorted(conversations.glob("*.db"), key=lambda p: p.stat().st_mtime) if conversations.is_dir() else []
    if not dbs:
        return None
    live = dbs[-1]
    copy = into / "c.db"
    shutil.copy2(live, copy)
    wal = live.with_name(live.name + "-wal")
    if wal.exists():
        # The -shm is NOT copied, on purpose. See the module docstring.
        shutil.copy2(wal, into / "c.db-wal")
    return copy


def readable(blob: bytes | None) -> str:
    if not blob:
        return ""
    return " ".join(part.decode("ascii", "replace") for part in READABLE.findall(blob))


def describe(payload: bytes | None) -> tuple[str, str]:
    text = readable(payload)
    match = ACTION.search(text)
    summary = match.group(1) if match else ""
    # The tool name is the identifier immediately preceding the arguments object. Taking the first
    # bare identifier instead picks up prose from the model's own text - it produced "now" and
    # "been" against a live run - and a wrong tool name in a trajectory viewer is worse than none,
    # because it invents a call that was never made.
    name = ""
    before = TOOL_BEFORE_ARGS.search(text)
    if before:
        name = before.group(1)
    return name, summary


def rows(db: pathlib.Path, after: int) -> list[tuple]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(
            "select idx, step_type, status, step_payload from steps where idx > ? order by idx",
            (after,),
        ).fetchall()
    except sqlite3.DatabaseError as err:
        print(f"(snapshot unreadable: {err})", file=sys.stderr, flush=True)
        return []
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_home", type=pathlib.Path, help="the run's HOME (…/<run-id>/home)")
    parser.add_argument("--follow", "-f", action="store_true")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--width", type=int, default=150)
    args = parser.parse_args()

    seen = -1
    last: list[tuple[str, str]] = [("", "")]
    with tempfile.TemporaryDirectory(prefix="agy-trail-") as tmp:
        into = pathlib.Path(tmp)
        while True:
            for stale in into.glob("c.db*"):
                stale.unlink()
            db = snapshot(args.run_home, into)
            if db is None:
                print("(no conversation database yet)", flush=True)
            else:
                for idx, step_type, status, payload in rows(db, seen):
                    name, summary = describe(payload)
                    seen = max(seen, idx)
                    # agy records a call and its result as two steps carrying the same summary.
                    # Printing both doubles the trajectory and makes a run look twice as long as
                    # it was, which is exactly the wrong impression for a viewer used to judge
                    # whether a lane is spending its turns well.
                    if (name, summary) == last[0]:
                        continue
                    last[0] = (name, summary)
                    line = f"{idx:4}  {name:<14} {summary}"
                    print(line[: args.width], flush=True)
            if not args.follow:
                return 0
            time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
