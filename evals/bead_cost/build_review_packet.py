#!/usr/bin/env python3
"""Build the blinded packet the qualitative reviewers read, identically for every one of them.

The comparison being run is between REVIEWERS as much as between implementations, and that only
means anything if all of them read the same bytes. So the packet is built once, hashed, and the
hash is printed: a reviewer given a different packet is not a second opinion, it is a second
experiment.

WHAT IS AND IS NOT IN IT

Production code only. Test files are excluded from every entry, for two reasons that point the same
way: the question is about the design of the implementation, which passes 1 and 2 have already
cleared of defects; and the reference entry changed no test file at all, so including tests would
make the entries structurally different in a way that has nothing to do with their quality.

THE REFERENCE ENTRY IS NOT LABELLED, and it is not a control either. The commit that actually
landed this bead is placed among the others under the same kind of letter, and no reviewer is told
it exists - but it was produced the same way the candidates were, by an agent working on a
repository that took dozens of commits the same day, and the only thing marking it as good is that
it was merged. So where the panel puts it falsifies nothing: last is a claim about that
implementation, not about the review. What falsifies the exercise is whether the reviewers agree
with each other at all, and whether the blinding held.

BLINDING, mechanically rather than by good intentions:

  - entries are lettered, and the letter-to-source mapping is derived from a seed that is written to
    a key file the reviewers never see;
  - commit messages never appear - only diffs, and the runs write their own commit messages;
  - run ids, model names, account suffixes and any path under the run root are absent by
    construction, because nothing but the diff text is copied;
  - the order is seeded rather than natural, so "first" carries no meaning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import subprocess
import sys

# The implementations under review, one per arm: the MEDIAN run by output tokens within its arm.
# Median rather than best or first, because every other rule is a choice about which run represents
# the arm, and this one is re-derivable from the artefacts by anybody.
IMPLEMENTATIONS = [
    ("kimi-k2.7", "llmux-kimi-06"),
    ("gemini-3.7-flash", "llmux-agy-02"),
    ("sonnet", "llmux-claude-04"),
    ("deepseek-pro-high", "llmux-dshigh-03"),
]

PRODUCTION_ONLY = ["--", "*.go", ":(exclude)*_test.go"]


def git(args: list[str], cwd: pathlib.Path) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def work_tree(run_dir: pathlib.Path, here: pathlib.Path) -> pathlib.Path:
    """The tree the run actually worked in, which is not always the one it was launched in."""
    found = subprocess.run([str(here / "find-work.sh"), str(run_dir / "llmux"), str(run_dir)],
                           capture_output=True, text=True)
    if found.returncode == 0 and found.stdout.strip():
        return pathlib.Path(found.stdout.strip())
    return run_dir / "llmux"


def implementation_diff(tree: pathlib.Path, base_ref: str) -> str:
    """Everything the run changed in production code, committed or not.

    Untracked files are included as their full text. A run that solves the bead in a new file and
    never commits leaves all of its work outside `git diff`, and one of the four did exactly that -
    137 lines that no diff would have shown.
    """
    parts = []
    committed = git(["diff", base_ref, "HEAD", *PRODUCTION_ONLY], tree)
    if committed.strip():
        parts.append(committed)
    working = git(["diff", "HEAD", *PRODUCTION_ONLY], tree)
    if working.strip():
        parts.append(working)
    for name in git(["ls-files", "--others", "--exclude-standard"], tree).split():
        if not name.endswith(".go") or name.endswith("_test.go"):
            continue
        body = (tree / name).read_text(errors="replace")
        parts.append(f"--- /dev/null\n+++ b/{name}\n" +
                     "".join(f"+{line}\n" for line in body.splitlines()))
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=pathlib.Path, default=pathlib.Path.home() / "tmp/bead-cost")
    ap.add_argument("--subject", type=pathlib.Path, default=pathlib.Path.home() / "repositories/llmux")
    ap.add_argument("--base", default="64cfb7e")
    ap.add_argument("--gold", default="3d6a5a2")
    ap.add_argument("--seed", type=int, required=True,
                    help="fixes the lettering; record it, and keep the key away from reviewers")
    ap.add_argument("--runs", default="",
                    help="arm=run,arm=run,... in place of the default median set. Replicating the "
                         "comparison needs a different run of each arm per packet, and the median "
                         "rule exists to pick ONE representative - which is the choice replication "
                         "removes rather than repeats.")
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()

    implementations = IMPLEMENTATIONS
    if args.runs:
        implementations = []
        for pair in args.runs.split(","):
            if "=" not in pair:
                print(f"build: --runs wants arm=run pairs, got {pair!r}", file=sys.stderr)
                return 1
            arm, run = pair.split("=", 1)
            implementations.append((arm.strip(), run.strip()))

    here = pathlib.Path(__file__).resolve().parent
    entries = []
    for arm, run in implementations:
        tree = work_tree(args.root / run, here)
        diff = implementation_diff(tree, "origin/main")
        if not diff.strip():
            print(f"build: {run} produced an empty diff - refusing to build a packet with a hole in it",
                  file=sys.stderr)
            return 1
        entries.append({"source": f"{arm} / {run}", "reference": False, "diff": diff})

    gold = git(["diff", args.base, args.gold, *PRODUCTION_ONLY], args.subject)
    if not gold.strip():
        print("build: the reference diff is empty; without it the result cannot be falsified",
              file=sys.stderr)
        return 1
    entries.append({"source": f"reference commit {args.gold}", "reference": True, "diff": gold})

    random.Random(args.seed).shuffle(entries)
    letters = [chr(ord("A") + i) for i in range(len(entries))]

    args.out.mkdir(parents=True, exist_ok=True)
    packet = ["# Implementations under review", "",
              "Each section is one implementation of the same task, as a unified diff against the "
              "same base commit. Test files are excluded: only production code is shown.", ""]
    for letter, entry in zip(letters, entries):
        packet += [f"## Implementation {letter}", "", "```diff", entry["diff"].rstrip(), "```", ""]

    body = "\n".join(packet)
    packet_path = args.out / "packet.md"
    packet_path.write_text(body)
    digest = hashlib.sha256(body.encode()).hexdigest()

    # Pass A reads one entry at a time, and it must be the SAME text the comparative packet shows,
    # cut from the same build. Producing the two from separate runs would let the seed, and with it
    # the lettering, drift between the passes that are meant to cross-check each other.
    for letter, entry in zip(letters, entries):
        (args.out / f"impl-{letter}.md").write_text(
            f"## Implementation {letter}\n\n```diff\n{entry['diff'].rstrip()}\n```\n")

    # The key never goes near a reviewer. It is written beside the packet so the answers can be
    # decoded afterwards, and so the lettering can be reproduced from the seed alone.
    (args.out / "KEY-do-not-show-reviewers.json").write_text(json.dumps({
        "seed": args.seed,
        "packet_sha256": digest,
        "mapping": {letter: entry["source"] for letter, entry in zip(letters, entries)},
        "reference_letter": next(l for l, e in zip(letters, entries) if e["reference"]),
    }, indent=2) + "\n")

    print("runs:   " + ", ".join(f"{arm}={run}" for arm, run in implementations))
    print(f"packet: {packet_path}  ({len(body):,} bytes)")
    print(f"sha256: {digest}")
    print(f"entries: {len(entries)} lettered {letters[0]}..{letters[-1]}")
    print("key written beside it; every reviewer must be given THIS file, unmodified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
