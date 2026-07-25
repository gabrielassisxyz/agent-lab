"""Experiment entrypoint: run the matrix with a real agent and write the results.

The core, `run_and_report`, takes an `agent_for` factory so it is testable with a
fake agent (no model call). `__main__` wires the real `ClaudeCliAgent` and is what a
human invokes to produce actual data:

    python3 -m evals.rule_adherence.run --reps 3 --model <id> --out results/rule-adherence

This is deliberately not run in CI (it makes real model calls and needs a sandbox);
CI covers `run_and_report` through the fake-agent path.

Every run is checkpointed under `--out`, and re-invoking the same command resumes it:
finished cells are skipped, errored ones are retried. That is what makes a long grid
survivable, and it is why `--out` is the identity of a run rather than just a
destination.

`--dry-run` prints the grid it would execute, with the size of the largest composed
prompt, and calls no model. A run whose cost nobody has looked at is a run nobody
decided to make.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .checkpoint import Checkpoint
from .context import estimate_tokens
from .matrix import AgentFor, results_document, run_matrix
from .placements import Axes, PLACEMENTS, compose, load_corpus
from .schema import Task, load_tasks
from .scoring import score

_HERE = Path(__file__).parent


def axes_grid(turns: tuple[int, ...], filler: tuple[int, ...], seed: int = 0) -> tuple[Axes, ...]:
    return tuple(Axes(turns=t, filler_tokens=f, seed=seed) for t in turns for f in filler)


def run_and_report(agent_for: AgentFor, out_dir: Path, reps: int = 1,
                   placements: tuple[str, ...] = PLACEMENTS,
                   axes_list: tuple[Axes, ...] = (Axes(),),
                   tasks: list[Task] | None = None,
                   resume: bool = True) -> Path:
    """Run the grid and write a timestamp-free results document. Returns the path
    written. The tasks and the sample corpus ship with the repo.
    """
    tasks = load_tasks(_HERE / "tasks.json") if tasks is None else tasks
    corpus = load_corpus(_HERE / "corpus.sample.json")
    out_dir.mkdir(parents=True, exist_ok=True)

    checkpoint = Checkpoint(out_dir) if resume else None
    outcomes = run_matrix(tasks, corpus, agent_for, placements=placements,
                          reps=reps, axes_list=axes_list, checkpoint=checkpoint)
    document = results_document(outcomes, score(outcomes))

    out_path = out_dir / "results.json"
    out_path.write_text(json.dumps(document, indent=2) + "\n")
    return out_path


def describe_grid(tasks: list[Task], placements: tuple[str, ...],
                  axes_list: tuple[Axes, ...], reps: int) -> str:
    """What a run would cost, before it is paid for.

    Reports the cell count and the largest composed prompt, because the two ways a
    grid surprises you are the number of calls and the size of each one.
    """
    corpus = load_corpus(_HERE / "corpus.sample.json")
    cells = len(tasks) * len(placements) * len(axes_list) * reps
    largest = 0
    total_turns = 0
    for task in tasks:
        for placement in placements:
            for axes in axes_list:
                session = compose(task.instruction, task.category, placement, corpus, axes)
                largest = max(largest, estimate_tokens(session.render()))
                total_turns += len(session.turns) * reps

    lines = [
        f"tasks:      {len(tasks)}",
        f"placements: {len(placements)} ({', '.join(placements)})",
        f"axes:       {len(axes_list)} ({', '.join(a.label() for a in axes_list)})",
        f"reps:       {reps}",
        f"cells:      {cells}",
        f"agent calls: {total_turns} (one per turn, per cell)",
        f"largest composed session: ~{largest} tokens (estimated, not billed)",
    ]
    return "\n".join(lines)


def _int_list(raw: str) -> tuple[int, ...]:
    return tuple(int(part) for part in raw.split(",") if part.strip())


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the rule-adherence matrix.")
    parser.add_argument("--reps", type=int, default=1, help="runs per cell (N>=3 for a real result)")
    parser.add_argument("--model", default=None, help="model id passed to the agent CLI")
    parser.add_argument("--out", type=Path, default=Path("results/rule-adherence"))
    parser.add_argument("--turns", type=_int_list, default=(1,),
                        help="comma-separated turn counts, e.g. 1,5,20,50")
    parser.add_argument("--filler", type=_int_list, default=(0,),
                        help="comma-separated filler sizes in estimated tokens, e.g. 0,8000,32000")
    parser.add_argument("--placements", default=",".join(PLACEMENTS),
                        help="comma-separated subset of placements to run")
    parser.add_argument("--tasks", default=None,
                        help="comma-separated task ids; defaults to the whole task-set")
    parser.add_argument("--no-resume", action="store_true",
                        help="ignore any checkpoint under --out and score only this run")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the grid and the largest prompt; call no model")
    args = parser.parse_args()

    placements = tuple(p for p in args.placements.split(",") if p.strip())
    axes_list = axes_grid(args.turns, args.filler)
    tasks = load_tasks(_HERE / "tasks.json")
    if args.tasks:
        wanted = {t.strip() for t in args.tasks.split(",") if t.strip()}
        tasks = [t for t in tasks if t.id in wanted]
        missing = wanted - {t.id for t in tasks}
        if missing:
            raise SystemExit(f"unknown task id(s): {sorted(missing)}")

    if args.dry_run:
        print(describe_grid(tasks, placements, axes_list, args.reps))
        return

    # Imported here so the module imports without the agent's dependencies present.
    from .cli_agent import ClaudeCliAgent

    def agent_for(task, placement):  # a fresh agent per cell
        return ClaudeCliAgent(model=args.model, extra_args=["--dangerously-skip-permissions"])

    path = run_and_report(agent_for, args.out, reps=args.reps, placements=placements,
                          axes_list=axes_list, tasks=tasks, resume=not args.no_resume)
    print(f"wrote {path}")


if __name__ == "__main__":
    _main()
