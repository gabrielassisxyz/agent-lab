"""Placement composer: assemble the session for a task under each placement, at a
chosen distance.

A placement decides WHERE the rules sit relative to the task instruction:

- no-rules          : the control. No rule text anywhere.
- front-load-all    : every rule in the static prefix.
- pruned-static     : only the short constitution in the prefix.
- jit-near-query    : only the task-relevant rules, in the tail, next to the instruction.
- hybrid            : constitution in the prefix + task-relevant rules in the tail.
- hybrid-enforcement: same text as hybrid; its extra leg is an external gate the
                      runner applies to the agent's tools, not prompt text.

**Why `no-rules` is an arm and not a footnote.** Without it there is no way to tell a
rule being followed from a model that would have done the right thing anyway. Five of
the six tasks in the first task-set passed under every placement, which reads as
"placement does not matter" but actually means those tasks never measured rule
adherence at all. The control turns that from a judgement call into a measurement,
and it doubles as the admission test for the task-set (see `screening.py`).

**Why filler is identical across arms.** The rules move; nothing else does. If a
longer arm also carried more padding, any difference would confound placement with
context length, and the experiment could not say which caused what. So the same
`Axes` produce the same turn count and the same filler in every arm, and the only
variable is where the rule text lands.

The retrieval step (which rules are "task-relevant") is a deterministic
classify-by-category: a task's category selects the rules of that category. That is
the v1 matcher; a sharper one is future work, and keeping it deterministic is what
lets these placements be unit-tested.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .context import assert_inert, filler_text, filler_turns

PLACEMENTS = (
    "no-rules",
    "front-load-all",
    "pruned-static",
    "jit-near-query",
    "hybrid",
    "hybrid-enforcement",
)

# The control arm, named once so callers do not spell it. Screening and scoring both
# treat it differently from the arms under test.
CONTROL = "no-rules"

# The "constitution": the always-on core that the pruned prefix keeps. Safety-critical
# rules are the ones the evidence says must always be present (and separately gated).
CONSTITUTION_CATEGORIES = frozenset({"safety-critical"})

# Turn 0 of a multi-turn session needs to be a real message. This framing is byte
# identical in every arm, so it cannot itself be the thing that moves a score.
_PRIMING = ("Here is the background for this session. Read it, acknowledge in one line, "
            "and wait for the task.")


@dataclass(frozen=True)
class Axes:
    """The distance knobs for one cell.

    `turns` is the total number of user turns; the task always arrives on the last
    one. `filler_tokens` is inert padding placed after the prefix, an estimate in
    tokens (see `context.CHARS_PER_TOKEN`), never a reported cost.
    """

    turns: int = 1
    filler_tokens: int = 0
    seed: int = 0

    def label(self) -> str:
        """A stable identifier for this point in the axis space, for checkpoint keys."""
        return f"t{self.turns}-f{self.filler_tokens}"


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    trigger: str
    text: str


@dataclass(frozen=True)
class Session:
    """The ordered user turns of one cell. The last turn carries the task."""

    turns: list[str] = field(default_factory=list)

    def render(self) -> str:
        """The whole session as one string. For a single-turn cell that is the prompt;
        for a longer one it is a readable record of what was sent.
        """
        return "\n\n".join(t for t in self.turns if t)


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


def _rule_blocks(task_category: str, placement: str, corpus: list[Rule]) -> tuple[str, str]:
    """Return (prefix_block, tail_block) for a placement."""
    prefix_header = "Project rules (always apply):"
    tail_header = "Rules relevant to this task:"
    matched = relevant_rules(task_category, corpus)

    if placement == CONTROL:
        return "", ""
    if placement == "front-load-all":
        return _render_rules(corpus, prefix_header), ""
    if placement == "pruned-static":
        return _render_rules(_constitution(corpus), prefix_header), ""
    if placement == "jit-near-query":
        return "", _render_rules(matched, tail_header)
    # hybrid and hybrid-enforcement compose identically; the enforcement arm differs
    # by the gate the runner applies, not by its text.
    return _render_rules(_constitution(corpus), prefix_header), _render_rules(matched, tail_header)


def compose(instruction: str, task_category: str, placement: str, corpus: list[Rule],
            axes: Axes | None = None) -> Session:
    """Build the session for one cell.

    A single turn (the default) yields prefix + filler + instruction + tail, which is
    the original single-prompt shape when there is no filler. More turns push the
    prefix back in time: rules land on turn 0, padding turns follow, and the task
    arrives last, which is the distance the design's memory/state axis asks about.
    """
    if placement not in PLACEMENTS:
        raise ValueError(f"unknown placement {placement!r}; known: {PLACEMENTS}")
    axes = axes or Axes()
    if axes.turns < 1:
        raise ValueError(f"a session needs at least one turn; got {axes.turns}")

    prefix, tail = _rule_blocks(task_category, placement, corpus)
    padding = filler_text(axes.filler_tokens, seed=axes.seed)
    if padding:
        assert_inert(padding)

    if axes.turns == 1:
        return Session([_join(prefix, padding, instruction, tail)])

    opening = _join(prefix, padding, _PRIMING)
    middle = filler_turns(axes.turns - 2, seed=axes.seed + 1)
    for turn in middle:
        assert_inert(turn)
    return Session([opening, *middle, _join(instruction, tail)])


def _join(*parts: str) -> str:
    return "\n\n".join(p for p in parts if p)


def enforces_gate(placement: str) -> bool:
    """Whether the runner should apply the external enforcement gate for this placement.
    Only hybrid-enforcement does; the rest rely on prompt text alone.
    """
    return placement == "hybrid-enforcement"
