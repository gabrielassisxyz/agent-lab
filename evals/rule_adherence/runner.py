"""The runner: turn one (task, placement, axes, agent) into a scored outcome.

The pipeline:

    stage repo state (task.setup) -> compose the session for the placement and axes ->
    install the command shim (blocking, for the enforcement arm) -> drive the agent ->
    reduce its trajectory into an AgentResult -> run the checker

Everything is real and deterministic given the agent: the repo is a throwaway git
repo in a temp dir, the base sha and base branch are captured after setup so only the
agent's own work is attributed to it, and the checker is deterministic code. Driving
a fake agent makes the whole pipeline testable without a model.

Two things here are load-bearing and easy to get wrong:

- **The shim lives outside the repo.** Put it inside and it becomes an untracked file
  in the very repo a "clean up the stray files" task is scored on, so the instrument
  would be planting the evidence it then measures.
- **A failed agent call is not a passing cell.** An empty trajectory satisfies every
  "did not do the forbidden thing" checker, so a rate-limited or timed-out call would
  score as perfect adherence. Those cells are recorded as errored, never scored, and
  left for a resume to retry.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import gitshim
from .agent import Agent
from .checkers import get_checker
from .placements import Axes, Rule, compose, enforces_gate
from .schema import CheckOutcome, Task, Usage
from .trajectory import build_result, current_branch, list_branches

# Files the padding turns can actually read. Without them a filler turn asks about
# something that does not exist, and the context it adds is an apology rather than
# the tool output that dilutes a real session.
_FIXTURE_FILES = {
    "inventory_reconciliation.py": (
        "def reconcile(rows, window_days=14):\n"
        '    """Fold the rolling window into one summary row per region."""\n'
        "    return [r for r in rows if r.get('quantity') is not None]\n"
    ),
    "pricing_cache.py": (
        "CACHE_TTL_SECONDS = 900\n\n\n"
        "def lookup(sku, snapshot):\n"
        '    """Fall back to the previous snapshot when the feed is late."""\n'
        "    return snapshot.get(sku)\n"
    ),
    "shipment_planner.py": (
        "def plan(orders, lead_time_days):\n"
        '    """Round to whole units after applying the factor."""\n'
        "    return sorted(orders, key=lambda o: o['due'])\n"
    ),
}


@dataclass(frozen=True)
class RunOutcome:
    task_id: str
    placement: str
    rep: int = 0
    axes: Axes = field(default_factory=Axes)
    outcome: CheckOutcome | None = None
    enforcement_applied: bool = False
    usage: Usage = field(default_factory=Usage)
    error: str | None = None
    # What was sent and what came back. Kept so a failed cell can be read rather than
    # guessed at: the Opus run left 18 failures with no trajectory behind them, which
    # is why its single failure mode could not be explained.
    trace: dict = field(default_factory=dict)

    @property
    def errored(self) -> bool:
        return self.error is not None


def _git(repo_dir: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True, text=True)


def _init_repo(repo_dir: Path) -> None:
    repo_dir.mkdir(parents=True, exist_ok=True)
    _git(repo_dir, "init", "-q", "-b", "master")
    _git(repo_dir, "config", "user.email", "runner@agent-lab.local")
    _git(repo_dir, "config", "user.name", "agent-lab runner")
    # Hermetic on purpose: point hooks at an empty dir so the operator's global
    # commit-msg / pre-commit hooks never fire in a fixture repo. Enforcement in this
    # experiment is applied deliberately by the runner (the hybrid-enforcement
    # placement), never by whatever hooks the host machine happens to carry -- which
    # would otherwise block a commit a task needs to stage and silently skew a cell.
    nohooks = repo_dir / ".nohooks"
    nohooks.mkdir(exist_ok=True)
    _git(repo_dir, "config", "core.hooksPath", str(nohooks))
    (repo_dir / "README.md").write_text("# fixture repo\n")
    for name, body in _FIXTURE_FILES.items():
        (repo_dir / name).write_text(body)
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-q", "-m", "chore: initial fixture")


def _head_sha(repo_dir: Path) -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True)
    return out.stdout.strip()


def run_task(task: Task, placement: str, agent: Agent, corpus: list[Rule],
             axes: Axes | None = None, rep: int = 0,
             workdir: Path | None = None) -> RunOutcome:
    """Run one cell of the matrix. If `workdir` is given the cell is created under it
    (useful for inspection); otherwise a temp dir is used and cleaned up.
    """
    if workdir is not None:
        return _run_in(Path(workdir), task, placement, agent, corpus, axes, rep)
    with tempfile.TemporaryDirectory(prefix="agent-lab-") as tmp:
        return _run_in(Path(tmp), task, placement, agent, corpus, axes, rep)


def _run_in(cell_dir: Path, task: Task, placement: str, agent: Agent, corpus: list[Rule],
            axes: Axes | None, rep: int) -> RunOutcome:
    axes = axes or Axes()
    # The repo is one subdirectory of the cell, so the shim and its log sit beside it
    # and never show up in the repo the checkers read.
    repo_dir = cell_dir / "repo"
    _init_repo(repo_dir)
    if task.setup:
        # The setup stages the starting state; it runs before the base sha is taken,
        # so whatever it creates or commits is the ground the agent starts from, not
        # something attributed to the agent.
        subprocess.run(task.setup, cwd=repo_dir, shell=True, check=True,
                       capture_output=True, text=True)
    base_sha = _head_sha(repo_dir)
    base_branch = current_branch(repo_dir)
    base_branches = list_branches(repo_dir)

    gate = enforces_gate(placement)
    shim = gitshim.install(cell_dir / "shim", cell_dir / "git-commands.log", block=gate)

    session = compose(task.instruction, task.category, placement, corpus, axes)
    run = agent.run(session.turns, repo_dir, env=shim.env)

    common = {
        "task_id": task.id, "placement": placement, "rep": rep, "axes": axes,
        "enforcement_applied": gate, "usage": run.usage,
    }
    trace = {"turns": session.turns, "events": run.events, "shim_commands": shim.commands()}
    if run.error is not None:
        return RunOutcome(error=run.error, trace=trace, **common)

    result = build_result(run.events, repo_dir, base_sha, base_branch=base_branch,
                          usage=run.usage, shim_commands=shim.commands(),
                          base_branches=base_branches)
    trace |= {
        "commands": result.commands, "commit_messages": result.commit_messages,
        "branch": result.branch, "base_branch": result.base_branch,
        "branches_created": result.branches_created,
        "final_text": result.final_text,
    }
    return RunOutcome(outcome=get_checker(task.checker)(result), trace=trace, **common)
