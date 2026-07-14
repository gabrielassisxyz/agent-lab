#!/usr/bin/env python3
"""Score every run of a noise-floor batch and report the dispersion.

The output is the point of the whole exercise: **how much does one configuration disagree with
itself?** Resolve rate answers it at one bit per run, which is why the continuous signals are
reported next to it — a configuration that resolves 10/10 but swings between 30 and 90 turns is
not stable, and a scaffold whose effect is smaller than that swing cannot be measured with one
run per cell.

File- and node-retrieval are the PolyBench metrics, computed here from the predicted patch
against the gold patch. They are the sharpest instrument we have for the scaffolding question,
because a scaffold should improve *navigation* (does the agent find the right file?) before it
improves *resolution* — and navigation is graded, while pass/fail is binary.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FORK = Path.home() / "repositories" / "_cloned" / "SWE-bench-fork"

FILE_RE = re.compile(r"^diff --git a/(\S+) b/\S+", re.M)
# A hunk header carries the enclosing function/class in its trailing context, e.g.
# `@@ -12,7 +12,9 @@ def estimate(self):` — that is what "node" means here.
NODE_RE = re.compile(r"^@@ .* @@\s*(?:def|class)\s+(\w+)", re.M)


def files_in(patch: str) -> set[str]:
    return set(FILE_RE.findall(patch))


def nodes_in(patch: str) -> set[str]:
    return set(NODE_RE.findall(patch))


def prf(pred: set, gold: set) -> tuple[float, float]:
    if not gold:
        return (0.0, 0.0)
    tp = len(pred & gold)
    recall = tp / len(gold)
    precision = tp / len(pred) if pred else 0.0
    return round(recall, 2), round(precision, 2)


def score(preds: Path, instance: str, dataset: str, split: str, run_id: str) -> bool:
    """Run the official scorer. The verdict comes from its report file, not from its exit code."""
    subprocess.run(
        [str(FORK / ".venv/bin/python"), "-m", "swebench.harness.run_evaluation",
         "--dataset_name", dataset, "--split", split,
         "--predictions_path", str(preds), "--instance_ids", instance,
         "--cache_level", "instance", "--run_id", run_id, "--namespace", "swerebench"],
        cwd=FORK, capture_output=True, text=True)
    model = json.loads(preds.read_text())["model_name_or_path"]
    report = FORK / f"{model}.{run_id}.json"
    if not report.exists():
        return False
    data = json.loads(report.read_text())
    return instance in data.get("resolved_ids", [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default="pgmpy__pgmpy-3137")
    ap.add_argument("--model", default="kimi-k2.7")
    ap.add_argument("--dataset", default="nebius/SWE-rebench-leaderboard")
    ap.add_argument("--split", default="2026_03")
    args = ap.parse_args()

    from datasets import load_dataset
    inst = next(r for r in load_dataset(args.dataset, split=args.split)
                if r["instance_id"] == args.instance)
    gold_files, gold_nodes = files_in(inst["patch"]), nodes_in(inst["patch"])

    outdir = REPO / "results" / "noise-floor" / args.instance / args.model
    rows = []
    for pred in sorted(outdir.glob("preds-*.jsonl")):
        n = int(pred.stem.split("-")[1])
        run = json.loads((outdir / f"run-{n:02d}.json").read_text())
        resolved = score(pred, args.instance, args.dataset, args.split,
                         f"nf-{args.model}-{n:02d}")
        fr, fp = prf(files_in(run["patch"]), gold_files)
        nr, npz = prf(nodes_in(run["patch"]), gold_nodes)
        # A timed-out run has no turns and no patch. It is kept in the table and excluded from
        # the spreads: it is a fact about the environment (an upstream backoff ate the run),
        # not a fact about how the agent solves the task. Folding it into the medians would
        # blame the model for the plumbing.
        rows.append({"run": n, "resolved": resolved, "timeout": bool(run.get("timeout")),
                     "turns": run.get("turns"),
                     "tools": run.get("tool_calls"), "wall_s": run.get("wall_time_s"),
                     "patch_lines": len(run["patch"].splitlines()),
                     "file_recall": fr, "file_prec": fp, "node_recall": nr,
                     "tokens_out": run.get("tokens_out")})
        if rows[-1]["timeout"]:
            print(f"  run {n:02d}  TIMEOUT (upstream backoff) — excluded from spreads",
                  flush=True)
        else:
            print(f"  run {n:02d}  resolved={str(resolved):<5} turns={rows[-1]['turns']:>3} "
                  f"wall={rows[-1]['wall_s']:>6}s  patch={rows[-1]['patch_lines']:>3}L  "
                  f"file_recall={fr} prec={fp}", flush=True)

    (outdir / "summary.json").write_text(json.dumps(rows, indent=2))

    ok = [r for r in rows if not r["timeout"]]

    def spread(key: str) -> str:
        vals = [r[key] for r in ok if isinstance(r.get(key), (int, float))]
        if len(vals) < 2:
            return "n/a"
        ratio = max(vals) / min(vals) if min(vals) else float("inf")
        return (f"min={min(vals)} max={max(vals)} median={statistics.median(vals)} "
                f"sd={statistics.stdev(vals):.1f}  ({ratio:.1f}x)")

    n_res = sum(r["resolved"] for r in ok)
    n_to = len(rows) - len(ok)
    print(f"\n=== {args.model} on {args.instance} ===")
    print(f"  runs          : {len(rows)} ({len(ok)} completed, {n_to} timed out upstream)")
    print(f"  resolve rate  : {n_res}/{len(ok)} of the completed runs")
    print(f"  turns         : {spread('turns')}")
    print(f"  patch lines   : {spread('patch_lines')}")
    print(f"  file recall   : {spread('file_recall')}")
    print(f"  wall seconds  : {spread('wall_s')}   <-- NOT a clean signal: it includes time "
          f"spent waiting on upstream rate limits, so it measures the queue as much as the agent")
    print("\nResolve rate is one bit per run. The spreads are the noise floor: any effect you "
          "intend to measure downstream must be larger than these, or you are measuring noise.")


if __name__ == "__main__":
    main()
