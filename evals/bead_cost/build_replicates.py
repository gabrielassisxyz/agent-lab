#!/usr/bin/env python3
"""Build one packet per replicate, drawing a different run of every arm into each.

WHY REPLICATE AT ALL. A single packet compares one run of each arm, so a position in it is a claim
about that run and only inferentially about the arm behind it. Run-to-run spread inside an arm was
13 to 23 percent in output tokens during the campaign, which is not a spread anyone should assume
away. Five packets, each holding a different run of every arm, turn "this run ranked second" into
"this arm ranked second in four replicates out of five" - or expose that it does not.

WHY THE DRAW IS SEEDED AND WRITTEN DOWN. Pairing by run index would work, since the comparison is
within a packet and a packet of uniformly-early runs is still internally valid. It is avoided anyway:
run numbers are chronological, the accounts rotate across them, and nobody has ruled out that
something drifted over the night. A seeded draw removes the question for free, and the manifest is
what makes the removal checkable rather than claimed.

EACH PACKET GETS ITS OWN LETTERING SEED, which is not bookkeeping. The same arm lands on a different
letter in every replicate, so a reviewer that formed an opinion about "entry C" in one packet carries
nothing usable into the next.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import subprocess
import sys

# Arm label as it appears in the key, mapped to the run-directory prefix it was launched under.
ARMS = {
    "kimi-k2.7": "llmux-kimi",
    "gemini-3.7-flash": "llmux-agy",
    "sonnet": "llmux-claude",
    "deepseek-pro-high": "llmux-dshigh",
}


def usable_runs(root: pathlib.Path, prefix: str) -> list[str]:
    """Runs of one arm that produced a scored, building, fully passing tree.

    Derived rather than listed. Two directories in this campaign hold launches that never became
    runs - one with an empty record, one that died on an api_error after two seconds - and a
    hardcoded list of "the five good ones" is a list that stops being true the next time the
    campaign is extended.
    """
    found = []
    for directory in sorted(root.glob(f"{prefix}-*")):
        if not re.fullmatch(rf"{re.escape(prefix)}-\d+", directory.name):
            continue
        verdict = directory / "verdict.json"
        if not verdict.exists():
            continue
        try:
            value = json.loads(verdict.read_text())
        except ValueError:
            continue
        if value.get("build_failed") or not value.get("scored"):
            continue
        if value.get("passed") != value.get("total"):
            continue
        found.append(directory.name)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=pathlib.Path, default=pathlib.Path.home() / "tmp/bead-cost")
    ap.add_argument("--out-root", type=pathlib.Path, required=True,
                    help="one directory per replicate is created under this")
    ap.add_argument("--replicates", type=int, default=5)
    ap.add_argument("--draw-seed", type=int, required=True,
                    help="fixes which run of each arm lands in which packet; goes in the manifest")
    args = ap.parse_args()

    here = pathlib.Path(__file__).resolve().parent
    pool = {arm: usable_runs(args.root, prefix) for arm, prefix in ARMS.items()}

    short = {arm: runs for arm, runs in pool.items() if len(runs) < args.replicates}
    if short:
        for arm, runs in short.items():
            print(f"build-replicates: {arm} has {len(runs)} usable runs, needs {args.replicates}: "
                  f"{runs}", file=sys.stderr)
        return 1

    # Drawn WITHOUT replacement, so no run is reviewed twice and every replicate is a fresh sample
    # of each arm. Reusing a run across packets would let one lucky or unlucky sample carry weight
    # in more than one replicate, which is the thing replication exists to stop.
    draw = random.Random(args.draw_seed)
    order = {arm: draw.sample(runs, len(runs)) for arm, runs in pool.items()}

    args.out_root.mkdir(parents=True, exist_ok=True)
    manifest = {"draw_seed": args.draw_seed, "replicates": [], "pool": pool}

    for index in range(args.replicates):
        assignment = {arm: order[arm][index] for arm in ARMS}
        lettering_seed = args.draw_seed * 100 + index + 1
        out = args.out_root / f"replicate-{index + 1}"
        runs_arg = ",".join(f"{arm}={run}" for arm, run in assignment.items())
        result = subprocess.run(
            [str(here / "build_review_packet.py"), "--seed", str(lettering_seed),
             "--runs", runs_arg, "--out", str(out)],
            capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stdout + result.stderr, file=sys.stderr)
            print(f"build-replicates: replicate {index + 1} failed; nothing further was built",
                  file=sys.stderr)
            return 1
        digest = next((line.split()[1] for line in result.stdout.splitlines()
                       if line.startswith("sha256:")), "")
        manifest["replicates"].append({
            "replicate": index + 1, "packet": str(out), "lettering_seed": lettering_seed,
            "runs": assignment, "packet_sha256": digest,
        })
        print(f"replicate {index + 1}: {out.name}  sha256 {digest[:12]}…  " +
              "  ".join(f"{arm.split('-')[0]}={run.rsplit('-', 1)[1]}"
                        for arm, run in assignment.items()))

    manifest_path = args.out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nmanifest: {manifest_path}")
    print("every packet still carries a KEY beside it; review-isolate.sh moves each one out before "
          "a reviewer can see it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
