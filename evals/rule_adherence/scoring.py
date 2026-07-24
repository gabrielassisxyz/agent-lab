"""Aggregate run outcomes into per-placement scores (Phase 3/4).

Given the flat list of `RunOutcome`s the matrix produced, this reduces them to one
`PlacementScore` per placement: how often the rule held, and the distribution of the
ways it failed. Comparing those scores across placements is the whole point of the
experiment (front-load-all vs pruned-static vs hybrid, etc.).

A note on the "two-way" scoring the design calls for (per-rule compliance AND
all-or-nothing instance success): in the current task-set each task exercises exactly
one rule, so per-run pass rate *is* per-rule compliance, and instance success
collapses onto it. The scissors gap between the two only opens once an instance
carries several rules at once; the histogram of failure modes is what stays
informative in the meantime, and is deliberately not flattened into a single number.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from .runner import RunOutcome


@dataclass(frozen=True)
class PlacementScore:
    placement: str
    n: int
    passes: int
    pass_rate: float
    failure_modes: dict[str, int]  # mode -> count, over the failed runs


def score(outcomes: list[RunOutcome]) -> list[PlacementScore]:
    by_placement: dict[str, list[RunOutcome]] = defaultdict(list)
    for outcome in outcomes:
        by_placement[outcome.placement].append(outcome)

    scores: list[PlacementScore] = []
    for placement, runs in sorted(by_placement.items()):
        n = len(runs)
        passes = sum(1 for r in runs if r.outcome.passed)
        modes = Counter(r.outcome.failure_mode for r in runs if not r.outcome.passed)
        scores.append(PlacementScore(
            placement=placement,
            n=n,
            passes=passes,
            pass_rate=passes / n if n else 0.0,
            failure_modes=dict(modes),
        ))
    return scores
