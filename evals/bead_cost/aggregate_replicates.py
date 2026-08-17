#!/usr/bin/env python3
"""Read the comparative pass across replicate packets, and say whether an arm holds its position.

ONE PACKET ANSWERS A NARROWER QUESTION THAN IT LOOKS. It ranks the runs it contains, and an arm is
behind each run only inferentially. This reads several packets, each holding a different run of every
arm, and reports the position each ARM held in each replicate - which is the question the campaign
actually asks.

WHAT THE NUMBERS ARE FOR, in the order they should be read:

  1. The position table. Five rows of the same ordering is a result nobody needs a test to see, and
     that is the outcome worth hoping for. Read this first and let the rest support it.
  2. Kendall's W, an effect size from 0 to 1: how much the blocks agree on one ordering. It answers
     "how strong", which is the question significance never answers.
  3. Friedman, which answers only "could this much agreement come from arms that are interchangeable"
     - not which arm beats which, and not whether the difference matters.

THE MEASUREMENT FLOOR BELONGS BESIDE ALL THREE. Repeating the comparative pass three times against
one unchanged packet moved no entry at all: swing 0 on every position, with mean rank wandering by
half a rank unit. So movement seen here is the runs, not the panel - and a gap thinner than half a
rank unit is not a gap this instrument can resolve, however many replicates it is averaged over.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from aggregate_review import load_json  # noqa: E402


def chi2_sf(x: float, df: int) -> float:
    """P(X > x) for a chi-square with df degrees of freedom, in the standard library.

    The regularized upper incomplete gamma Q(df/2, x/2), by series below the transition point and by
    continued fraction above it. Written out rather than imported because every other script here
    runs on the standard library alone, and a statistics dependency added for one p-value is a
    dependency the next machine has to be told about.
    """
    if x <= 0:
        return 1.0
    a, z = df / 2.0, x / 2.0
    if z < a + 1.0:                                    # series for the LOWER function, then flip
        term = total = 1.0 / a
        for n in range(1, 1000):
            term *= z / (a + n)
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return 1.0 - total * math.exp(-z + a * math.log(z) - math.lgamma(a))
    tiny = 1e-300                                      # Lentz's continued fraction for the upper
    b, c, d = z + 1.0 - a, 1.0 / tiny, 1.0 / (z + 1.0 - a)
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h * math.exp(-z + a * math.log(z) - math.lgamma(a))


def ranks_with_ties(values: dict[str, float]) -> dict[str, float]:
    """Rank a block, giving tied entries their average rank.

    Ties are not hypothetical here: two arms can land on the same mean rank inside one replicate,
    and breaking the tie by dictionary order would invent an ordering the reviewers never gave.
    """
    order = sorted(values, key=lambda k: values[k])
    out: dict[str, float] = {}
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
            stop += 1
        shared = (index + stop) / 2.0 + 1.0
        for position in range(index, stop + 1):
            out[order[position]] = shared
        index = stop + 1
    return out


def friedman(blocks: list[dict[str, float]]) -> tuple[float, int, float, float]:
    """Friedman chi-square, degrees of freedom, p, and Kendall's W over ranked blocks.

    Every block must score the same treatments. A block is one complete ordering: one replicate's
    aggregate, or one reviewer's answer within one replicate, depending on what is being asked.
    """
    treatments = sorted(blocks[0])
    n, k = len(blocks), len(treatments)
    totals = {t: 0.0 for t in treatments}
    for block in blocks:
        ranked = ranks_with_ties(block)
        for t in treatments:
            totals[t] += ranked[t]
    chi = (12.0 / (n * k * (k + 1))) * sum(v * v for v in totals.values()) - 3.0 * n * (k + 1)
    df = k - 1
    kendall_w = chi / (n * (k - 1)) if n * (k - 1) else 0.0
    return chi, df, chi2_sf(chi, df), kendall_w


def arm_of(source: str) -> str:
    """The key records `arm / run`, or the reference with no run. Both are treatments here."""
    return source.split(" / ")[0].strip() if " / " in source else source.strip()


def replicate_rankings(answers: pathlib.Path, mapping: dict) -> dict[str, list[str]]:
    """Per reviewer, its ordering of ARMS rather than of letters."""
    out: dict[str, list[str]] = {}
    for path in sorted(answers.glob("passB-*.txt")):
        answer = load_json(path.read_text(errors="replace"), "ranking")
        if not answer or not isinstance(answer.get("ranking"), list):
            print(f"  WARNING  {path.stem} in {answers.name} has no usable ranking", file=sys.stderr)
            continue
        letters = [str(x).strip().upper()[:1] for x in answer["ranking"]]
        if sorted(letters) != sorted(mapping):
            print(f"  WARNING  {path.stem} in {answers.name} ranked {letters}, not the packet's "
                  f"{sorted(mapping)}", file=sys.stderr)
            continue
        out[path.stem.split("-", 1)[1]] = [arm_of(mapping[le]) for le in letters]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=pathlib.Path, help="written by build_replicates.py")
    ap.add_argument("--answers-root", type=pathlib.Path, required=True,
                    help="holds one directory per replicate, named as the packet directory is")
    ap.add_argument("--key-store", type=pathlib.Path,
                    default=pathlib.Path.home() / "tmp/bead-cost-review-keys")
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    per_replicate: list[tuple[int, dict[str, list[str]]]] = []

    for entry in manifest["replicates"]:
        name = pathlib.Path(entry["packet"]).name
        key_path = args.key_store / f"{name}.json"
        answers = args.answers_root / name
        if not key_path.exists():
            print(f"  MISSING  key for {name} at {key_path}", file=sys.stderr)
            continue
        if not answers.is_dir():
            print(f"  MISSING  answers for {name} at {answers}", file=sys.stderr)
            continue
        key = json.loads(key_path.read_text())
        if key.get("packet_sha256") and entry.get("packet_sha256") \
                and key["packet_sha256"] != entry["packet_sha256"]:
            print(f"  MISMATCH {name}: the key was written for a different packet than the manifest "
                  f"records; refusing to decode it", file=sys.stderr)
            continue
        rankings = replicate_rankings(answers, key["mapping"])
        if rankings:
            per_replicate.append((entry["replicate"], rankings))

    if len(per_replicate) < 2:
        print("fewer than two replicates could be read; nothing to compare", file=sys.stderr)
        return 1

    arms = sorted({a for _, r in per_replicate for order in r.values() for a in order})

    width = max(len(a) for a in arms) + 2
    print("=== where each arm landed, per replicate ===")
    print("  " + " " * width + "  ".join(f"rep {n}" for n, _ in per_replicate) + "     mean  swing")
    block_by_replicate: list[dict[str, float]] = []
    positions: dict[str, list[float]] = {a: [] for a in arms}
    for _, rankings in per_replicate:
        mean_rank = {a: statistics.mean([order.index(a) + 1 for order in rankings.values()])
                     for a in arms}
        block_by_replicate.append(mean_rank)
    for index, (_, rankings) in enumerate(per_replicate):
        ordering = sorted(arms, key=lambda a: block_by_replicate[index][a])
        for a in arms:
            positions[a].append(ordering.index(a) + 1)
    for a in sorted(arms, key=lambda x: statistics.mean(positions[x])):
        row = "  ".join(f"{int(p):5d}" for p in positions[a])
        swing = max(positions[a]) - min(positions[a])
        print(f"  {a:{width}s}{row}   {statistics.mean(positions[a]):6.2f}  {swing:5d}")

    print("\n=== the ordering each replicate would have reported ===")
    for index, (n, _) in enumerate(per_replicate):
        ordering = sorted(arms, key=lambda a: block_by_replicate[index][a])
        print(f"  replicate {n}: " + "  ".join(
            f"{a}({block_by_replicate[index][a]:.2f})" for a in ordering))

    print("\n=== agreement ===")
    chi, df, p, w = friedman(block_by_replicate)
    print(f"  blocks = replicates ({len(block_by_replicate)}), treatments = arms ({len(arms)})")
    print(f"    Kendall W = {w:.2f}   Friedman chi2 = {chi:.2f}, df {df}, p = {p:.4f}")

    # Every (reviewer, replicate) pair produced one complete ordering, which is far more blocks. The
    # same reviewer appears in each replicate, so the blocks are NOT independent and the p is
    # optimistic; it is reported because the W beside it is still a fair summary of agreement.
    fine_blocks = [{a: float(order.index(a) + 1) for a in arms}
                   for _, rankings in per_replicate for order in rankings.values()]
    chi2_, df2, p2, w2 = friedman(fine_blocks)
    print(f"  blocks = reviewer x replicate ({len(fine_blocks)}), NOT independent - p is optimistic")
    print(f"    Kendall W = {w2:.2f}   Friedman chi2 = {chi2_:.2f}, df {df2}, p = {p2:.4f}")

    print("\n=== read against the measurement floor ===")
    print("  Repeating the same packet three times moved no position at all (swing 0), with mean")
    print("  rank wandering by 0.5. Movement above is the runs; a gap under 0.5 is not resolvable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
