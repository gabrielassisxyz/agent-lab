#!/usr/bin/env python3
"""Score every run of a noise-floor batch and report the dispersion.

The output is the point of the whole exercise: **how much does one configuration disagree with
itself?** Resolve rate answers it at one bit per run, which is why the continuous signals are
reported next to it — a configuration that resolves 10/10 but swings between 30 and 90 turns is
not stable, and a scaffold whose effect is smaller than that swing cannot be measured with one
run per cell.

File- and node-retrieval are the PolyBench metrics, computed here from the predicted patch
against the gold patch. Node retrieval comes from `nodes.py`, which reads the AST — an earlier
version read the label in the hunk header and was structurally incapable of scoring anything but
zero. See design.md §10b.

**Retrieval *precision* is not a quality signal, and must not be read as one.** It measures
conformity to the gold patch, which is one human's fix, not the set of correct fixes. On
`pgmpy__pgmpy-3137` the repo carries two parallel implementations of the same logic and the agent
repairs both, where the gold patch repairs one: precision is 0.5 on every run, and the agent is
arguably the more thorough of the two. Recall is the signal; precision is a note.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from pathlib import Path

from nodes import base_files, files_in, nodes_in

REPO = Path(__file__).resolve().parent.parent
FORK = Path.home() / "repositories" / "_cloned" / "SWE-bench-fork"
BASE_CACHE = REPO / ".cache" / "base-files"


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

    outdir = REPO / "results" / "noise-floor" / args.instance / args.model
    runs = {int(p.stem.split("-")[1]): json.loads(p.read_text())
            for p in sorted(outdir.glob("run-*.json"))}

    # Node retrieval needs the files as they were *before* the patch, and the prebuilt eval image
    # is the authority on that: it is the exact tree the agent worked on, it is local, and it
    # cannot drift from what was actually run. Every file any patch touches is lifted once.
    touched = files_in(inst["patch"]) | {f for r in runs.values()
                                         for f in files_in(r.get("patch", ""))}
    base = base_files(inst["image_name"], touched, BASE_CACHE)
    gold_files, gold_nodes = files_in(inst["patch"]), nodes_in(inst["patch"], base)

    rows = []
    for pred in sorted(outdir.glob("preds-*.jsonl")):
        n = int(pred.stem.split("-")[1])
        run = runs[n]
        resolved = score(pred, args.instance, args.dataset, args.split,
                         f"nf-{args.model}-{n:02d}")
        fr, fp = prf(files_in(run["patch"]), gold_files)
        nr, np_ = prf(nodes_in(run["patch"], base), gold_nodes)
        # A timed-out run has no turns and no patch. It is kept in the table and excluded from
        # the spreads: it is a fact about the environment (an upstream backoff ate the run),
        # not a fact about how the agent solves the task. Folding it into the medians would
        # blame the model for the plumbing.
        rows.append({"run": n, "resolved": resolved, "timeout": bool(run.get("timeout")),
                     "turns": run.get("turns"),
                     "tools": run.get("tool_calls"), "wall_s": run.get("wall_time_s"),
                     "patch_lines": len(run["patch"].splitlines()),
                     "file_recall": fr, "file_prec": fp,
                     "node_recall": nr, "node_prec": np_,
                     "tokens_out": run.get("tokens_out")})
        if rows[-1]["timeout"]:
            print(f"  run {n:02d}  TIMEOUT (upstream backoff) — excluded from spreads",
                  flush=True)
        else:
            print(f"  run {n:02d}  resolved={str(resolved):<5} turns={rows[-1]['turns']:>3} "
                  f"wall={rows[-1]['wall_s']:>6}s  patch={rows[-1]['patch_lines']:>3}L  "
                  f"file_recall={fr} node_recall={nr} (prec {fp}/{np_})", flush=True)

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
    print(f"  node recall   : {spread('node_recall')}")
    print(f"  wall seconds  : {spread('wall_s')}   <-- NOT a clean signal: it includes time "
          f"spent waiting on upstream rate limits, so it measures the queue as much as the agent")
    print(f"  retrieval prec: file={spread('file_prec')}")
    print(f"                  node={spread('node_prec')}")
    print("                  ^ conformity to the gold patch, NOT correctness — see the module "
          "docstring. Recall is the signal.")
    print("\nResolve rate is one bit per run. The spreads are the noise floor: any effect you "
          "intend to measure downstream must be larger than these, or you are measuring noise.")


if __name__ == "__main__":
    main()
