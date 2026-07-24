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

- **admissible** - fails the control and passes under at least one arm. This is the
  only kind of task a placement comparison may be computed from.
- **measures-prior** - passes the control at least once. The model does this
  unprompted, so the rule is not what is being measured. It is worth knowing which
  of a rule set falls here: those rules cost context and buy nothing.
- **unreachable-by-text** - fails the control and fails every arm. No placement of
  prose fixes it, which is precisely the evidence for putting that rule behind a
  deterministic gate instead of writing it more loudly.

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
            verdict=_verdict(control, control_rate, best_rate),
            control_n=len(control),
            control_pass_rate=control_rate,
            best_arm=best_arm,
            best_arm_pass_rate=best_rate,
        ))
    return screens


def _verdict(control: list[RunOutcome], control_rate: float, best_rate: float) -> str:
    if not control:
        # Without a control arm the question cannot be answered, and guessing an
        # answer here is how an unscreened task set gets treated as a screened one.
        return "not-screened"
    if control_rate > 0.0:
        return MEASURES_PRIOR
    if best_rate == 0.0:
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
