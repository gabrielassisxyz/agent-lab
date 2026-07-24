"""Run the experiment matrix (Phase 3): every task under every placement, repeated.

`run_matrix` is the orchestration Phase 2 (the adherence noise floor) and Phase 4
(scoring) sit on top of. It stays agnostic about the agent via `agent_for`, a factory
called once per cell: a real agent needs a fresh invocation per run, and the noise
floor is precisely the variance across the reps of one cell, so a factory (not a
shared instance) is the honest shape.

With a deterministic agent the reps are identical and the noise floor is zero by
construction; that is expected, and it is why the real, stochastic agent is what
makes Phase 2 meaningful. The aggregation and serialization here are exercised now
with a fake agent so the plumbing is proven before the expensive runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .agent import Agent
from .placements import PLACEMENTS, Rule
from .runner import RunOutcome, run_task
from .schema import Task
from .scoring import PlacementScore

# Called once per (task, placement, rep) to obtain the agent for that cell.
AgentFor = Callable[[Task, str], Agent]


def run_matrix(
    tasks: list[Task],
    corpus: list[Rule],
    agent_for: AgentFor,
    placements: tuple[str, ...] = PLACEMENTS,
    reps: int = 1,
    workdir: Path | None = None,
) -> list[RunOutcome]:
    outcomes: list[RunOutcome] = []
    for task in tasks:
        for placement in placements:
            for _ in range(reps):
                agent = agent_for(task, placement)
                outcomes.append(run_task(task, placement, agent, corpus, workdir))
    return outcomes


def results_document(outcomes: list[RunOutcome], scores: list[PlacementScore]) -> dict:
    """A JSON-serializable record of a matrix run: every cell plus the aggregates.
    Written to results/ so a run is reproducible and comparable to the next one.
    """
    return {
        "runs": [
            {
                "task": o.task_id,
                "placement": o.placement,
                "passed": o.outcome.passed,
                "failure_mode": o.outcome.failure_mode,
                "enforcement_applied": o.enforcement_applied,
            }
            for o in outcomes
        ],
        "scores": [
            {
                "placement": s.placement,
                "n": s.n,
                "passes": s.passes,
                "pass_rate": s.pass_rate,
                "failure_modes": s.failure_modes,
            }
            for s in scores
        ],
    }
