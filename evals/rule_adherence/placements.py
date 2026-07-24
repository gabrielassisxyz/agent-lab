"""Placement composer (Phase 1): assemble the prompt for a task under each of the
five placements the experiment compares (docs/experiments/rule-adherence.md).

A placement decides WHERE the rules sit relative to the task instruction:

- front-load-all   : every rule in the static prefix.
- pruned-static    : only the short constitution (safety-critical) in the prefix.
- jit-near-query   : only the task-relevant rules, in the tail, next to the instruction.
- hybrid           : constitution in the prefix + task-relevant rules in the tail.
- hybrid-enforcement: same text as hybrid; the enforcement leg is an external gate the
                     runner applies, not prompt text, so composition is identical.

The composed prompt is prefix + instruction + tail, so the tail is the text closest
to the generation point. The retrieval step (which rules are "task-relevant") is a
deterministic classify-by-category for now: a task's category selects the rules of
that category. That is the v1 matcher; a sharper one is future work, and keeping it
deterministic is what lets these placements be unit-tested.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PLACEMENTS = (
    "front-load-all",
    "pruned-static",
    "jit-near-query",
    "hybrid",
    "hybrid-enforcement",
)

# The "constitution": the always-on core that the pruned prefix keeps. Safety-critical
# rules are the ones the evidence says must always be present (and separately gated).
CONSTITUTION_CATEGORIES = frozenset({"safety-critical"})


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    trigger: str
    text: str


@dataclass(frozen=True)
class ComposedPrompt:
    prefix: str        # the cacheable static block
    instruction: str   # the task's own request
    tail: str          # rules injected next to the query (empty for static placements)

    def render(self) -> str:
        parts = [p for p in (self.prefix, self.instruction, self.tail) if p]
        return "\n\n".join(parts)


def load_corpus(path: Path | str) -> list[Rule]:
    raw = json.loads(Path(path).read_text())
    return [Rule(**entry) for entry in raw]


def _render_rules(rules: list[Rule], header: str) -> str:
    if not rules:
        return ""
    lines = [header] + [f"- {r.text}" for r in rules]
    return "\n".join(lines)


def relevant_rules(task_category: str, corpus: list[Rule]) -> list[Rule]:
    """The classify-by-category matcher: rules whose category matches the task's."""
    return [r for r in corpus if r.category == task_category]


def _constitution(corpus: list[Rule]) -> list[Rule]:
    return [r for r in corpus if r.category in CONSTITUTION_CATEGORIES]


def compose(instruction: str, task_category: str, placement: str, corpus: list[Rule]) -> ComposedPrompt:
    if placement not in PLACEMENTS:
        raise ValueError(f"unknown placement {placement!r}; known: {PLACEMENTS}")

    prefix_header = "Project rules (always apply):"
    tail_header = "Rules relevant to this task:"
    matched = relevant_rules(task_category, corpus)

    if placement == "front-load-all":
        return ComposedPrompt(_render_rules(corpus, prefix_header), instruction, "")
    if placement == "pruned-static":
        return ComposedPrompt(_render_rules(_constitution(corpus), prefix_header), instruction, "")
    if placement == "jit-near-query":
        return ComposedPrompt("", instruction, _render_rules(matched, tail_header))
    # hybrid and hybrid-enforcement compose identically: constitution prefix + JIT tail.
    return ComposedPrompt(
        _render_rules(_constitution(corpus), prefix_header),
        instruction,
        _render_rules(matched, tail_header),
    )


def enforces_gate(placement: str) -> bool:
    """Whether the runner should apply the external enforcement gate for this placement.
    Only hybrid-enforcement does; the rest rely on prompt text alone.
    """
    return placement == "hybrid-enforcement"
