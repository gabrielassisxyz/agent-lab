"""Aggregate run outcomes into scores.

Two reductions, because the experiment asks two different questions.

`score` collapses everything to one row per placement: how often the rule held, how
it failed when it did not, what it cost, and how many cells never produced a verdict.
That is the "which placement" comparison.

`decay` keeps the axes: one row per (placement, turns, filler). That is the question
the whole instrument was rebuilt for, and it cannot be read off the collapsed table.
"Where does adherence break as the session grows" is a curve, and averaging over the
axis that defines the curve erases it.

Two rules that keep these numbers honest:

- **Errored cells are excluded from rates and counted separately.** A cell whose
  agent call failed produced no behaviour, and folding it in either direction invents
  a result. It is reported as `errored` so a table with many of them is visibly
  untrustworthy rather than quietly wrong.
- **Cost is reported as measured or not at all.** The token figures come from the
  CLI's own usage report; if an adapter does not provide one they stay zero, which
  reads as "not measured" rather than "free".
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

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
