"""The admission test: decide which tasks are allowed to measure anything.

A rule-adherence task is only evidence about *rule adherence* if the agent would
have got it wrong without the rule. If it passes with no rule in the context, it is
measuring what the model already does, and including it inflates every arm equally
while proving nothing. The first full run was five-sixths this: five of six tasks
passed under every placement, which reads as "placement does not matter" but means
"these tasks never tested it".

So every task is screened against the control arm before it is allowed into a
result, and the screening is a byproduct of the baseline sweep rather than a
separate expense. Three verdicts:

- **admissible** - the control leaves headroom AND some arm reaches the task. This
  is the only kind of task a placement comparison may be computed from.
- **measures-prior** - the control already passes most of the time. The model does
  this unprompted, so the rule is not what is being measured. It is worth knowing
  which of a rule set falls here: those rules cost context and buy nothing.
- **unreachable-by-text** - no arm gets near it. No placement of prose fixes it,
  which is precisely the evidence for putting that rule behind a deterministic gate
  instead of writing it more loudly.
- **not-screened** - the grid cannot answer the question, because the control arm or
  every arm under test is missing from it. A verdict is withheld rather than guessed,
  in both directions: a grid with no control cannot tell adherence from prior, and a
  control-only grid (which is what a noise-floor pass usually is) has tested no
  placement at all. Reporting the second as `unreachable-by-text` states the exact
  opposite of the truth, and states it in the shape of a measurement.

**Why a band and not a hard zero.** The strict reading ("admissible only if the
control never passes") is cleaner to state, and it is the wrong instrument for a
stochastic agent: it throws away exactly the tasks that sit in the middle, which are
the ones with measurable headroom. This lab already settled that question once, and
its answer is a band, not a point (`AGENTS.md`: task selection at a 30-70% pass rate
"is a precondition, not an optimization"). The same shape applies here, with the
control pass rate standing in for difficulty: a task is out if the model already
does it, and out if nothing reaches it, and in between it can be measured.

The number that matters for an admissible task is therefore the **effect**, the gap
between the best arm and the control, not the arm's absolute pass rate. An arm at
0.9 means nothing until you know the control was at 0.85.

Errored cells are excluded before any of this; a cell that failed to run is not a
cell that failed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .placements import CONTROL
from .runner import RunOutcome

ADMISSIBLE = "admissible"
MEASURES_PRIOR = "measures-prior"
UNREACHABLE = "unreachable-by-text"
NOT_SCREENED = "not-screened"

# The band, mirroring this lab's existing task-selection rule. Above the ceiling the
# model needs no rule; below the floor no placement reaches the task.
CONTROL_CEILING = 0.7
ARM_FLOOR = 0.3


@dataclass(frozen=True)
class TaskScreen:
    task_id: str
    verdict: str
    control_n: int
    control_pass_rate: float
    best_arm: str | None
    best_arm_pass_rate: float

    @property
    def admissible(self) -> bool:
        return self.verdict == ADMISSIBLE

    @property
    def effect(self) -> float:
        """How much the best placement bought over no rule at all. This, not the
        arm's absolute pass rate, is what an admissible task actually measures.
        """
        return self.best_arm_pass_rate - self.control_pass_rate


def screen(outcomes: list[RunOutcome]) -> list[TaskScreen]:
    """One verdict per task, from a sweep that included the control arm."""
    scored = [o for o in outcomes if not o.errored and o.outcome is not None]
    by_task: dict[str, list[RunOutcome]] = defaultdict(list)
    for outcome in scored:
        by_task[outcome.task_id].append(outcome)

    screens = []
    for task_id, runs in sorted(by_task.items()):
        control = [r for r in runs if r.placement == CONTROL]
        control_rate = _rate(control)
        best_arm, best_rate = _best_arm(runs)
        screens.append(TaskScreen(
            task_id=task_id,
            verdict=_verdict(control, control_rate, best_arm, best_rate),
            control_n=len(control),
            control_pass_rate=control_rate,
            best_arm=best_arm,
            best_arm_pass_rate=best_rate,
        ))
    return screens


def _verdict(control: list[RunOutcome], control_rate: float,
             best_arm: str | None, best_rate: float) -> str:
    if not control:
        # Without a control arm the question cannot be answered, and guessing an
        # answer here is how an unscreened task set gets treated as a screened one.
        return NOT_SCREENED
    if control_rate > CONTROL_CEILING:
        # Decidable from the control alone: it is a statement about the model's
        # prior, so a control-only grid answers it and answers it well.
        return MEASURES_PRIOR
    if best_arm is None:
        # No arm ran, so "no placement of prose reaches this" was never tested. A
        # noise-floor grid re-runs one cell at high reps and is often control-only;
        # reporting that as unreachable-by-text inverts the finding, and the
        # inversion is invisible because the verdict looks like a measurement.
        return NOT_SCREENED
    if best_rate < ARM_FLOOR:
        return UNREACHABLE
    return ADMISSIBLE


def _best_arm(runs: list[RunOutcome]) -> tuple[str | None, float]:
    by_placement: dict[str, list[RunOutcome]] = defaultdict(list)
    for run in runs:
        if run.placement != CONTROL:
            by_placement[run.placement].append(run)
    if not by_placement:
        return None, 0.0
    best = max(sorted(by_placement), key=lambda p: _rate(by_placement[p]))
    return best, _rate(by_placement[best])


def _rate(runs: list[RunOutcome]) -> float:
    if not runs:
        return 0.0
    return sum(1 for r in runs if r.outcome and r.outcome.passed) / len(runs)


def admissible_ids(screens: list[TaskScreen]) -> list[str]:
    return [s.task_id for s in screens if s.admissible]
