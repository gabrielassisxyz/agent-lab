"""Data shapes for the rule-adherence experiment (docs/experiments/rule-adherence.md).

A rule-adherence task is a triple: a realistic instruction, a rule it should
trigger, and a deterministic checker for whether the rule was followed. The
checker inspects an `AgentResult` — the trace of what the agent actually did — and
never a model's own judgement, so a task can fail informatively.

This module is the contract between three things built at different times: the
task-set (data), the checkers (Phase 0, here), and the runner that will produce
real `AgentResult`s from sandboxed runs (Phase 1). Keeping it dependency-free and
free of any agent coupling is deliberate: the checkers are unit-testable now,
against synthetic results, with no sandbox and no model call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class AgentResult:
    """What an agent did on one task, reduced to the facts a checker can decide on.

    Phase 1's runner fills this from a real trajectory; the checker tests fill it
    by hand. Every field is something observable in a trace, never an opinion about
    the trace.
    """

    final_text: str = ""                       # the agent's closing message
    commands: list[str] = field(default_factory=list)   # shell commands it ran, in order
    commit_messages: list[str] = field(default_factory=list)
    branch: str | None = None                  # the branch it committed on, if any
    pr_body: str | None = None
    files_read: list[str] = field(default_factory=list)
    reply_language: str | None = None          # ISO code, when the runner detects it


@dataclass(frozen=True)
class CheckOutcome:
    """A checker's verdict: did the rule hold, and if not, in which way it failed.

    `failure_mode` is drawn from the experiment's closed vocabulary so the matrix
    can aggregate failures by kind, not just count them. `None` on a pass.
    """

    passed: bool
    failure_mode: str | None = None            # one of FAILURE_MODES, or None on pass
    detail: str = ""                           # human-readable, for a failed run's log


# The closed failure vocabulary from the experiment design. A checker must return
# one of these (or None). "violation" = did the forbidden thing and owned it;
# "surface-compliance" = did it while reporting success without disclosing it —
# the single most dangerous mode, and the reason adherence is scored two ways.
FAILURE_MODES = frozenset(
    {"ignored", "violation", "surface-compliance", "wrong-convention", "not-consulted"}
)


@dataclass(frozen=True)
class Task:
    """One rule-adherence task. `checker` names a function in the checker registry;
    `setup` is a shell snippet the Phase 1 runner executes to stage repo state, and
    is inert here (Phase 0 tests the checkers, not the staging).
    """

    id: str
    category: str
    rule_id: str
    instruction: str
    checker: str
    setup: str = ""
    checker_args: dict = field(default_factory=dict)


def load_tasks(path: Path | str) -> list[Task]:
    """Load the task-set from a JSON array. Raises on an unknown field so a typo in
    a task file fails loudly rather than being silently dropped.
    """
    raw = json.loads(Path(path).read_text())
    tasks = [Task(**entry) for entry in raw]
    _assert_unique_ids(tasks)
    return tasks


def _assert_unique_ids(tasks: list[Task]) -> None:
    seen: set[str] = set()
    for task in tasks:
        if task.id in seen:
            raise ValueError(f"duplicate task id: {task.id!r}")
        seen.add(task.id)
