"""Aggregate run outcomes into scores.

Three reductions, because the experiment asks three different questions.

`score` collapses everything to one row per placement: how often the rule held, how
it failed when it did not, what it cost, and how many cells never produced a verdict.
It is the cheapest summary and the **weakest** comparison; see below.

`decay` keeps the axes: one row per (placement, turns, filler). That is the question
the whole instrument was rebuilt for, and it cannot be read off the collapsed table.
"Where does adherence break as the session grows" is a curve, and averaging over the
axis that defines the curve erases it.

`task_effects` and `arm_effects` are the comparison that should actually be read.

**Why paired, and why it is not a matter of taste.** Every arm runs every task, so the
design is paired, and analysing paired data as if it were not throws the pairing away.
Pooling counts 63 observations per arm as if they were 63 draws from one coin; they
are 21 tasks of very different difficulty, each drawn three times, so the honest unit
of analysis is the task and the honest n is 21. Measuring the effect *within* each
task makes every task its own control and cancels the difficulty spread that otherwise
shows up as noise.

The gain is large when tasks differ in difficulty and the effect is consistent, which
is the expected shape here. On a realistic six-task example the same data reads as 1.7
standard errors pooled and 5.0 paired: identical mean effect, roughly three times the
sensitivity, purely from not discarding the pairing.

Three rules that keep these numbers honest:

- **Errored cells are excluded from rates and counted separately.** A cell whose
  agent call failed produced no behaviour, and folding it in either direction invents
  a result. It is reported as `errored` so a table with many of them is visibly
  untrustworthy rather than quietly wrong.
- **Cost is reported as measured or not at all.** The token figures come from the
  CLI's own usage report; if an adapter does not provide one they stay zero, which
  reads as "not measured" rather than "free".
- **An effect is reported against the control, never as an absolute rate.** An arm at
  0.9 means nothing until you know the control was at 0.85.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .placements import CONTROL
from .runner import RunOutcome
from .schema import Usage


@dataclass(frozen=True)
class PlacementScore:
    placement: str
    n: int
    passes: int
    pass_rate: float
    failure_modes: dict[str, int]  # mode -> count, over the failed runs
    errored: int = 0
    usage: Usage = field(default_factory=Usage)

    @property
    def tokens_per_cell(self) -> float:
        total = self.usage.input_tokens + self.usage.output_tokens
        return total / self.n if self.n else 0.0


@dataclass(frozen=True)
class DecayPoint:
    placement: str
    turns: int
    filler_tokens: int
    n: int
    passes: int
    pass_rate: float
    errored: int = 0


def score(outcomes: list[RunOutcome]) -> list[PlacementScore]:
    by_placement: dict[str, list[RunOutcome]] = defaultdict(list)
    for outcome in outcomes:
        by_placement[outcome.placement].append(outcome)

    scores: list[PlacementScore] = []
    for placement, runs in sorted(by_placement.items()):
        scored = [r for r in runs if not r.errored and r.outcome is not None]
        n = len(scored)
        passes = sum(1 for r in scored if r.outcome.passed)
        modes = Counter(r.outcome.failure_mode for r in scored if not r.outcome.passed)
        total = Usage()
        for run in runs:
            total = total + run.usage
        scores.append(PlacementScore(
            placement=placement,
            n=n,
            passes=passes,
            pass_rate=passes / n if n else 0.0,
            failure_modes=dict(modes),
            errored=len(runs) - n,
            usage=total,
        ))
    return scores


@dataclass(frozen=True)
class TaskEffect:
    """What one placement bought on one task, against the control on that same task."""

    task_id: str
    placement: str
    control_rate: float
    arm_rate: float
    n_control: int
    n_arm: int

    @property
    def effect(self) -> float:
        return self.arm_rate - self.control_rate


@dataclass(frozen=True)
class ArmEffect:
    """One placement's effect across tasks, treating the task as the unit."""

    placement: str
    tasks: int
    mean_effect: float
    sd: float
    standard_error: float
    standard_errors: float | None   # mean / se; None when se is 0
    improved: int
    unchanged: int
    regressed: int


def task_effects(outcomes: list[RunOutcome], control: str = CONTROL) -> list[TaskEffect]:
    """One row per (task, arm): the arm's pass rate on that task minus the control's.

    A task is only comparable where both the arm and the control produced verdicts on
    it, so a task missing either side is skipped rather than compared against zero.
    """
    rates: dict[tuple[str, str], tuple[float, int]] = {}
    for (task_id, placement), runs in _by_task_and_placement(outcomes).items():
        rates[(task_id, placement)] = (_rate(runs), len(runs))

    effects: list[TaskEffect] = []
    for (task_id, placement), (arm_rate, n_arm) in sorted(rates.items()):
        if placement == control:
            continue
        baseline = rates.get((task_id, control))
        if baseline is None:
            continue
        control_rate, n_control = baseline
        effects.append(TaskEffect(
            task_id=task_id, placement=placement,
            control_rate=control_rate, arm_rate=arm_rate,
            n_control=n_control, n_arm=n_arm,
        ))
    return effects


def arm_effects(outcomes: list[RunOutcome], task_ids: list[str] | None = None,
                control: str = CONTROL) -> list[ArmEffect]:
    """Aggregate the per-task effects into one row per arm.

    `task_ids` restricts the comparison to the tasks entitled to be in it, which in
    practice is the set the screening admitted. Computing this over tasks the model
    passes without any rule would average real effects with structural zeros and
    report the result as a smaller effect.
    """
    wanted = set(task_ids) if task_ids is not None else None
    grouped: dict[str, list[float]] = defaultdict(list)
    for effect in task_effects(outcomes, control=control):
        if wanted is None or effect.task_id in wanted:
            grouped[effect.placement].append(effect.effect)

    rows: list[ArmEffect] = []
    for placement, values in sorted(grouped.items()):
        mean = statistics.fmean(values) if values else 0.0
        # A single task cannot have a spread, and neither can a set of identical
        # effects. Both leave the standard error at zero, which is reported as an
        # absent ratio rather than as infinite confidence: it is a small-sample
        # artifact, not evidence.
        sd = statistics.stdev(values) if len(values) > 1 else 0.0
        error = sd / (len(values) ** 0.5) if values and sd > 0 else 0.0
        rows.append(ArmEffect(
            placement=placement,
            tasks=len(values),
            mean_effect=mean,
            sd=sd,
            standard_error=error,
            standard_errors=(mean / error) if error > 0 else None,
            improved=sum(1 for v in values if v > 0),
            unchanged=sum(1 for v in values if v == 0),
            regressed=sum(1 for v in values if v < 0),
        ))
    return rows


def _by_task_and_placement(outcomes: list[RunOutcome]) -> dict[tuple[str, str], list[RunOutcome]]:
    buckets: dict[tuple[str, str], list[RunOutcome]] = defaultdict(list)
    for outcome in outcomes:
        if outcome.errored or outcome.outcome is None:
            continue
        buckets[(outcome.task_id, outcome.placement)].append(outcome)
    return buckets


def _rate(runs: list[RunOutcome]) -> float:
    return sum(1 for r in runs if r.outcome.passed) / len(runs) if runs else 0.0


def decay(outcomes: list[RunOutcome]) -> list[DecayPoint]:
    """One row per (placement, turns, filler): the shape of adherence over distance."""
    buckets: dict[tuple[str, int, int], list[RunOutcome]] = defaultdict(list)
    for outcome in outcomes:
        buckets[(outcome.placement, outcome.axes.turns, outcome.axes.filler_tokens)].append(outcome)

    points = []
    for (placement, turns, filler), runs in sorted(buckets.items()):
        scored = [r for r in runs if not r.errored and r.outcome is not None]
        passes = sum(1 for r in scored if r.outcome.passed)
        points.append(DecayPoint(
            placement=placement, turns=turns, filler_tokens=filler,
            n=len(scored), passes=passes,
            pass_rate=passes / len(scored) if scored else 0.0,
            errored=len(runs) - len(scored),
        ))
    return points
