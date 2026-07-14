#!/usr/bin/env python3
"""Run one agent, on one instance, N times — and measure how much it disagrees with itself.

This is deliberately NOT an experiment about skills, scaffolds or agents. It answers the one
question that sizes every experiment that follows: **how much does the same configuration vary
between identical runs?** If run-to-run noise is wider than the effects we intend to hunt (a
scaffold might move resolve rate by ~5 points), then any single-run comparison downstream is
noise wearing a number's clothes, and the whole matrix has to be redesigned around repeats.

Binary pass/fail across a handful of runs is close to uninformative on its own — five runs is
five coin flips. So every run also records continuous signals (turns, tool calls, tokens, wall
time, files touched), which have far more resolution and reveal instability even when the
verdicts happen to agree.

The agent runs inside the instance's own eval image, attached only to `--internal` docker
networks: it can reach LiteLLM and nothing else. See evals/sandbox/verify.sh — run it first.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO / "evals" / "agents"
RESULTS = REPO / "results"

# The agent is given the issue text and nothing else — no hints, no test names. `hints_text`
# is deliberately withheld: it often paraphrases the fix, and feeding it in would measure
# reading comprehension rather than software engineering.
PROMPT = """Solve the following issue in the repository at /testbed.

Make the smallest change that fixes it. Do not write new tests; the graders' tests are hidden
from you. When you are done, leave the fix in the working tree — do not commit.

<issue>
{problem_statement}
</issue>
"""


def litellm_key() -> str:
    out = subprocess.run(
        ["docker", "inspect", "litellm-litellm-1", "--format",
         "{{range .Config.Env}}{{println .}}{{end}}"],
        capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("LITELLM_MASTER_KEY="):
            return line.split("=", 1)[1]
    raise SystemExit("LITELLM_MASTER_KEY not found on the litellm container")


def load_instance(dataset: str, split: str, instance_id: str) -> dict:
    from datasets import load_dataset
    for row in load_dataset(dataset, split=split):
        if row["instance_id"] == instance_id:
            return row
    raise SystemExit(f"{instance_id} not in {dataset}:{split}")


def parse_events(stream: str) -> dict:
    """Pull the continuous signals out of pi's JSON event stream.

    Parsed defensively: an unknown or malformed event must not lose the run, because the patch
    (the thing being scored) is captured from git regardless of what the log says.
    """
    turns = tool_calls = 0
    tools: dict[str, int] = {}
    tokens_in = tokens_out = 0
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = ev.get("type")
        if etype == "turn_start":
            turns += 1
        elif etype == "tool_execution_start":
            tool_calls += 1
            name = ev.get("toolName", "?")
            tools[name] = tools.get(name, 0) + 1
        elif etype in ("message_end", "turn_end"):
            usage = (ev.get("message") or {}).get("usage") or {}
            tokens_in += usage.get("input", 0) or 0
            tokens_out += usage.get("output", 0) or 0
    return {"turns": turns, "tool_calls": tool_calls, "tools": tools,
            "tokens_in": tokens_in, "tokens_out": tokens_out}


def run_once(inst: dict, key: str, run_idx: int, timeout: int) -> dict:
    image = inst["docker_image"]
    prompt = PROMPT.format(problem_statement=inst["problem_statement"])
    name = f"wb-run-{inst['instance_id'].replace('__', '-')}-{run_idx}"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    # Two internal networks, so there is no route out: one carries LiteLLM, one carries nothing.
    # The agent's own tools (bash, edit, read, write) therefore cannot reach github and cannot
    # fetch the upstream PR that fixes the issue.
    cmd = [
        "docker", "run", "--name", name, "--network", "wb-llm",
        "-v", "wb-agent:/opt/agent:ro",
        "-v", f"{AGENTS_DIR}:/ext:ro",
        "-e", f"LITELLM_API_KEY={key}",
        "-e", "LITELLM_BASE_URL=http://litellm-litellm-1:4000/v1",
        "-e", "PI_OFFLINE=1", "-e", "HOME=/tmp",
        "--entrypoint", "bash", image, "-c",
        "export PATH=/opt/agent/bin:$PATH && cd /testbed && "
        "pi -e /ext/pi-litellm-provider.ts --model litellm/kimi-k2.7 "
        "-p --mode json --no-session --no-skills --no-context-files "
        f"{json.dumps(prompt)}",
    ]

    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    elapsed = round(time.time() - started, 1)

    # The patch is read from git, never from what the agent claims it did.
    diff = subprocess.run(
        ["docker", "exec", name, "bash", "-c", "cd /testbed && git add -A && git diff --cached"],
        capture_output=True, text=True).stdout
    files = subprocess.run(
        ["docker", "exec", name, "bash", "-c",
         "cd /testbed && git diff --cached --name-only"],
        capture_output=True, text=True).stdout.split()
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    metrics = parse_events(proc.stdout)
    return {
        "run": run_idx,
        "wall_time_s": elapsed,
        "exit_code": proc.returncode,
        "empty_patch": not diff.strip(),
        "files_touched": files,
        "patch": diff,
        "stderr_tail": proc.stderr[-500:] if proc.returncode else "",
        **metrics,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", default="pgmpy__pgmpy-3137")
    ap.add_argument("--dataset", default="nebius/SWE-rebench-leaderboard")
    ap.add_argument("--split", default="2026_03")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()

    inst = load_instance(args.dataset, args.split, args.instance)
    key = litellm_key()
    outdir = RESULTS / "noise-floor" / args.instance
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"instance {args.instance} | split {args.split} | created {inst['created_at'][:10]}")
    print(f"image    {inst['docker_image']}")
    print(f"runs     {args.runs}\n")

    for i in range(1, args.runs + 1):
        print(f"[run {i}/{args.runs}] ...", flush=True)
        try:
            res = run_once(inst, key, i, args.timeout)
        except subprocess.TimeoutExpired:
            res = {"run": i, "timeout": True, "empty_patch": True, "patch": "",
                   "wall_time_s": args.timeout, "files_touched": []}
        (outdir / f"run-{i:02d}.json").write_text(json.dumps(res, indent=2))
        print(f"  {res['wall_time_s']}s | turns={res.get('turns')} "
              f"tools={res.get('tool_calls')} files={len(res['files_touched'])} "
              f"empty_patch={res['empty_patch']}", flush=True)

    # One predictions file per run: the scorer keys on instance_id, so ten runs of the same
    # instance cannot share a file.
    for i in range(1, args.runs + 1):
        res = json.loads((outdir / f"run-{i:02d}.json").read_text())
        (outdir / f"preds-{i:02d}.jsonl").write_text(json.dumps({
            "instance_id": args.instance,
            "model_name_or_path": f"pi-kimi-k2.7-run{i:02d}",
            "model_patch": res["patch"],
        }) + "\n")

    print(f"\nwrote {args.runs} runs + predictions to {outdir}")


if __name__ == "__main__":
    main()
