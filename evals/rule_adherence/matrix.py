"""Run the experiment matrix: every task, under every placement, at every point on
the axes, repeated.

`run_matrix` is the orchestration the noise floor and the scoring sit on top of. It
stays agnostic about the agent via `agent_for`, a factory called once per cell: a
real agent needs a fresh invocation per run, and the noise floor is precisely the
variance across the reps of one cell, so a factory (not a shared instance) is the
honest shape.

**On the shape of the grid.** The design lists four axes crossed with placements,
categories and reps, which is tens of thousands of cells per model and days of wall
clock. Crossing them fully is not a plan, it is an intention. So the grid this runs
is whatever list of `Axes` the caller passes, and the intended use is one factor at a
time from a baseline: sweep the placements at one point to find which tasks
discriminate, then move a single axis at a time over that reduced set. The code does
not enforce that, because it is a decision about what to spend, not a property of
the runner. It does make it cheap: every cell is checkpointed, so a sweep can be
stopped, resumed and extended without repeating work.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from .agent import Agent
from .checkpoint import Checkpoint, cell_key
from .placements import Axes, PLACEMENTS, Rule
from .runner import RunOutcome, run_task
from .schema import Task
from .scoring import DecayPoint, PlacementScore, arm_effects, decay, score, task_effects
from .screening import TaskScreen, admissible_ids, screen

# Called once per cell to obtain the agent for it.
AgentFor = Callable[[Task, str], Agent]


def run_matrix(
    tasks: list[Task],
    corpus: list[Rule],
    agent_for: AgentFor,
    placements: tuple[str, ...] = PLACEMENTS,
    reps: int = 1,
    axes_list: tuple[Axes, ...] = (Axes(),),
    checkpoint: Checkpoint | None = None,
    workdir: Path | None = None,
    on_cell: Callable[[RunOutcome], None] | None = None,
) -> list[RunOutcome]:
    """Run the grid, recording each cell as it finishes.

    With a checkpoint, cells already recorded are skipped and the return value is
    everything on disk, so a resumed run is indistinguishable from one that never
    stopped. Without one, the behaviour is the original in-memory sweep.

    **The rep is the outermost loop, and that is the point.** A sweep is hours long
    and stopping early is the expected case, not the exception, so what matters is
    what an interrupted run leaves behind. Sweeping the whole grid once per rep
    leaves every task and every arm covered at fewer reps - noisy, but a grid the
    screening can read. Finishing each cell's reps before moving on would instead
    leave the first tasks complete and the rest untouched, and screening has nothing
    to say about a prefix of the task-set. The results are identical either way; only
    the order in which they arrive changes, and order enters no part of the analysis.
    """
    done = checkpoint.completed() if checkpoint else set()
    fresh: list[RunOutcome] = []

    for rep in range(reps):
        for task in tasks:
            for placement in placements:
                for axes in axes_list:
                    if cell_key(task.id, placement, axes, rep) in done:
                        continue
                    agent = agent_for(task, placement)
                    outcome = run_task(task, placement, agent, corpus,
                                       axes=axes, rep=rep, workdir=workdir)
                    if checkpoint:
                        checkpoint.record(outcome)
                    if on_cell:
                        on_cell(outcome)
                    fresh.append(outcome)

    return checkpoint.outcomes() if checkpoint else fresh


def results_document(outcomes: list[RunOutcome], scores: list[PlacementScore],
                     decay_points: list[DecayPoint] | None = None,
                     screens: list[TaskScreen] | None = None) -> dict:
    """A JSON-serializable record of a matrix run: every cell plus the aggregates.

    The screening block is not decoration. A placement table computed over tasks that
    pass without any rule is a number with nothing behind it, so the document carries
    the evidence for which tasks were entitled to be in it, and the paired comparison
    is computed over exactly those tasks.

    **`effects` is the block to read, not `scores`.** Scores pool every observation
    per arm as if they came from one coin; the design is paired, every arm runs every
    task, and the honest unit is the task. An empty `effects` list with a populated
    `screening` block is not a broken run, it is the finding that no task in the set
    was entitled to be compared.
    """
    decay_points = decay(outcomes) if decay_points is None else decay_points
    screens = screen(outcomes) if screens is None else screens
    admitted = admissible_ids(screens)
    return {
        "admissible_tasks": admitted,
        "effects": [
            {
                "placement": e.placement,
                "tasks": e.tasks,
                "mean_effect": e.mean_effect,
                "sd": e.sd,
                "standard_error": e.standard_error,
                "standard_errors": e.standard_errors,
                "improved": e.improved,
                "unchanged": e.unchanged,
                "regressed": e.regressed,
            }
            for e in arm_effects(outcomes, task_ids=admitted)
        ],
        "task_effects": [
            {
                "task": e.task_id,
                "placement": e.placement,
                "control_rate": e.control_rate,
                "arm_rate": e.arm_rate,
                "effect": e.effect,
                "n_control": e.n_control,
                "n_arm": e.n_arm,
            }
            for e in task_effects(outcomes)
        ],
        "runs": [
            {
                "task": o.task_id,
                "placement": o.placement,
                "rep": o.rep,
                "turns": o.axes.turns,
                "filler_tokens": o.axes.filler_tokens,
                "passed": None if o.outcome is None else o.outcome.passed,
                "failure_mode": None if o.outcome is None else o.outcome.failure_mode,
                "enforcement_applied": o.enforcement_applied,
                "error": o.error,
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
                "errored": s.errored,
                "input_tokens": s.usage.input_tokens,
                "output_tokens": s.usage.output_tokens,
                "cache_read_tokens": s.usage.cache_read_tokens,
                "cache_write_tokens": s.usage.cache_write_tokens,
            }
            for s in scores
        ],
        "decay": [
            {
                "placement": d.placement,
                "turns": d.turns,
                "filler_tokens": d.filler_tokens,
                "n": d.n,
                "passes": d.passes,
                "pass_rate": d.pass_rate,
                "errored": d.errored,
            }
            for d in decay_points
        ],
        "screening": [
            {
                "task": s.task_id,
                "verdict": s.verdict,
                "control_n": s.control_n,
                "control_pass_rate": s.control_pass_rate,
                "best_arm": s.best_arm,
                "best_arm_pass_rate": s.best_arm_pass_rate,
            }
            for s in screens
        ],
    }
