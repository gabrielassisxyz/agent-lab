"""The runner (Phase 1): turn one (task, placement, agent) into a scored outcome.

The pipeline, per the experiment design:

    stage repo state (task.setup) -> compose the prompt for the placement ->
    drive the agent -> reduce its trajectory into an AgentResult -> run the checker

Everything is real and deterministic given the agent: the repo is a throwaway git
repo in a temp dir, the base sha is captured after setup so only the agent's own
commits are attributed to it, and the checker is the Phase 0 code. Driving a fake
agent makes the whole pipeline testable without a model; driving a real one is the
same call.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .agent import Agent
from .checkers import get_checker
from .placements import Rule, compose, enforces_gate
from .schema import CheckOutcome, Task
from .trajectory import build_result


@dataclass(frozen=True)
class RunOutcome:
    task_id: str
    placement: str
    outcome: CheckOutcome
    enforcement_applied: bool


def _git(repo_dir: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True, text=True)


def _init_repo(repo_dir: Path) -> None:
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
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-q", "-m", "chore: initial fixture")


def _head_sha(repo_dir: Path) -> str:
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, capture_output=True, text=True)
    return out.stdout.strip()


def run_task(task: Task, placement: str, agent: Agent, corpus: list[Rule], workdir: Path | None = None) -> RunOutcome:
    """Run one cell of the matrix. If `workdir` is given the repo is created under it
    (useful for inspection); otherwise a temp dir is used and cleaned up.
    """
    if workdir is not None:
        return _run_in(Path(workdir), task, placement, agent, corpus)
    with tempfile.TemporaryDirectory(prefix="agent-lab-") as tmp:
        return _run_in(Path(tmp), task, placement, agent, corpus)


def _run_in(repo_dir: Path, task: Task, placement: str, agent: Agent, corpus: list[Rule]) -> RunOutcome:
    _init_repo(repo_dir)
    if task.setup:
        # The setup stages the starting state; it runs before the base sha is taken,
        # so whatever it creates or commits is the ground the agent starts from, not
        # something attributed to the agent.
        subprocess.run(task.setup, cwd=repo_dir, shell=True, check=True, capture_output=True, text=True)
    base_sha = _head_sha(repo_dir)

    prompt = compose(task.instruction, task.category, placement, corpus).render()
    events = agent.run(prompt, repo_dir)
    result = build_result(events, repo_dir, base_sha)

    outcome = get_checker(task.checker)(result)
    return RunOutcome(
        task_id=task.id,
        placement=placement,
        outcome=outcome,
        enforcement_applied=enforces_gate(placement),
    )
