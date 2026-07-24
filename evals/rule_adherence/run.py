"""Experiment entrypoint: run the matrix with a real agent and write the results.

The core, `run_and_report`, takes an `agent_for` factory so it is testable with a
fake agent (no model call). `__main__` wires the real `ClaudeCliAgent` and is what a
human invokes to produce actual data:

    python3 -m evals.rule_adherence.run --reps 3 --model <id> --out results/rule-adherence

This is deliberately not run in CI (it makes real model calls and needs a sandbox);
CI covers `run_and_report` through the fake-agent path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .matrix import AgentFor, results_document, run_matrix
from .placements import PLACEMENTS, load_corpus
from .scoring import score
from .schema import load_tasks

_HERE = Path(__file__).parent


def run_and_report(agent_for: AgentFor, out_dir: Path, reps: int = 1,
                   placements: tuple[str, ...] = PLACEMENTS) -> Path:
    """Run the full matrix and write a timestamp-free results document. Returns the
    path written. The tasks and the sample corpus ship with the repo.
    """
    tasks = load_tasks(_HERE / "tasks.json")
    corpus = load_corpus(_HERE / "corpus.sample.json")
    outcomes = run_matrix(tasks, corpus, agent_for, placements=placements, reps=reps)
    document = results_document(outcomes, score(outcomes))

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "results.json"
    out_path.write_text(json.dumps(document, indent=2) + "\n")
    return out_path


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the rule-adherence matrix.")
    parser.add_argument("--reps", type=int, default=1, help="runs per cell (N>=3 for a real result)")
    parser.add_argument("--model", default=None, help="model id passed to the agent CLI")
    parser.add_argument("--out", type=Path, default=Path("results/rule-adherence"))
    args = parser.parse_args()

    # Imported here so the module imports without the agent's dependencies present.
    from .cli_agent import ClaudeCliAgent

    def agent_for(task, placement):  # a fresh agent per cell
        return ClaudeCliAgent(model=args.model, extra_args=["--dangerously-skip-permissions"])

    path = run_and_report(agent_for, args.out, reps=args.reps)
    print(f"wrote {path}")


if __name__ == "__main__":
    _main()
