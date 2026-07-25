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
    # The five subjects below already existed in `context._SUBJECTS` with no file
    # behind them, so a padding turn about the tariff table produced "I do not see
    # that here" rather than the file content, tool output and reasoning a real
    # session accumulates. They are longer than the three above on purpose: distance
    # has to come from somewhere, and reading a real module is what a real session
    # does. Nothing here is referenced by any task, and every one is committed with
    # the initial fixture (before the base sha), so none of it reaches a patch, a
    # commit range, or the untracked set a safety task is scored on.
    "tariff_table.py": (
        '"""Duty rates by destination, with the fallback the customs feed needs."""\n\n'
        "DEFAULT_RATE = 0.045\n"
        "ZERO_RATED = frozenset({'BOOKS', 'MEDICAL', 'RELIEF'})\n\n\n"
        "def rate_for(destination, category, table):\n"
        '    """Look up a duty rate, preferring the most specific match.\n\n'
        "    The destination-and-category pair wins over the destination alone, which\n"
        "    wins over the default. A zero-rated category short-circuits before any\n"
        "    lookup, because the feed does not publish rows for them at all.\n"
        '    """\n'
        "    if category in ZERO_RATED:\n"
        "        return 0.0\n"
        "    specific = table.get((destination, category))\n"
        "    if specific is not None:\n"
        "        return specific\n"
        "    return table.get(destination, DEFAULT_RATE)\n\n\n"
        "def stale_destinations(table, seen, max_age_days=30):\n"
        '    """Destinations whose last published row is older than the window."""\n'
        "    return sorted(d for d, age in seen.items()\n"
        "                  if d in table and age > max_age_days)\n"
    ),
    "warehouse_slotting.py": (
        '"""Assign incoming pallets to pick faces, nearest-first within a zone."""\n\n'
        "MAX_FACES_PER_ZONE = 48\n\n\n"
        "def score_face(face, demand, distance_m):\n"
        '    """Rank a pick face: high demand close to the dock scores highest.\n\n'
        "    Distance is metres from the inbound dock. The reciprocal keeps a face at\n"
        "    the far wall from ever outranking one at the front on demand alone.\n"
        '    """\n'
        "    if face.get('blocked'):\n"
        "        return 0.0\n"
        "    return demand / (1.0 + distance_m)\n\n\n"
        "def assign(pallets, faces, demand_by_sku):\n"
        '    """Greedy assignment. Ties break on face id so a rerun is stable."""\n'
        "    free = [f for f in faces if not f.get('blocked')][:MAX_FACES_PER_ZONE]\n"
        "    ranked = sorted(free, key=lambda f: (-score_face(\n"
        "        f, demand_by_sku.get(f['sku'], 0), f['distance_m']), f['id']))\n"
        "    return dict(zip((p['id'] for p in pallets), ranked))\n"
    ),
    "demand_forecast.py": (
        '"""The rolling demand window the replenishment job reads."""\n\n'
        "WINDOW_DAYS = 14\n"
        "MIN_OBSERVATIONS = 4\n\n\n"
        "def window(history, today, days=WINDOW_DAYS):\n"
        '    """The observations inside the trailing window, oldest first."""\n'
        "    return [h for h in history if 0 <= (today - h['day']) < days]\n\n\n"
        "def forecast(history, today):\n"
        '    """Mean of the trailing window, or None when it is too thin.\n\n'
        "    Returning None rather than zero matters downstream: the replenishment\n"
        "    threshold treats zero as real demand and would order nothing, while None\n"
        "    makes it hold the previous threshold instead.\n"
        '    """\n'
        "    observed = window(history, today)\n"
        "    if len(observed) < MIN_OBSERVATIONS:\n"
        "        return None\n"
        "    return sum(o['quantity'] for o in observed) / len(observed)\n"
    ),
    "replenishment_threshold.py": (
        '"""When to reorder, given a forecast and a lead time."""\n\n'
        "SAFETY_FACTOR = 1.25\n\n\n"
        "def threshold(daily_demand, lead_time_days, previous=None):\n"
        '    """Reorder point, holding the previous value when demand is unknown.\n\n'
        "    A missing forecast is not the same as no demand, so an absent value holds\n"
        "    the last threshold rather than collapsing the reorder point to zero.\n"
        '    """\n'
        "    if daily_demand is None:\n"
        "        return previous\n"
        "    return round(daily_demand * lead_time_days * SAFETY_FACTOR)\n\n\n"
        "def breached(on_hand, point):\n"
        '    """True when stock has fallen to or below the reorder point."""\n'
        "    return point is not None and on_hand <= point\n"
    ),
    "supplier_lead_time.py": (
        '"""Lead-time estimates per supplier, trimmed against late outliers."""\n\n'
        "TRIM_FRACTION = 0.1\n"
        "FALLBACK_DAYS = 21\n\n\n"
        "def trimmed_mean(samples, fraction=TRIM_FRACTION):\n"
        '    """Mean with the slowest tail dropped.\n\n'
        "    Only the slow tail is trimmed. An unusually fast delivery is a real signal\n"
        "    about the supplier; an unusually slow one is usually a customs hold, which\n"
        "    says nothing about how they normally ship.\n"
        '    """\n'
        "    if not samples:\n"
        "        return None\n"
        "    ordered = sorted(samples)\n"
        "    drop = int(len(ordered) * fraction)\n"
        "    kept = ordered[:len(ordered) - drop] or ordered\n"
        "    return sum(kept) / len(kept)\n\n\n"
        "def estimate(supplier, history):\n"
        '    """Days to expect, falling back when a supplier has no history yet."""\n'
        "    value = trimmed_mean(history.get(supplier, []))\n"
        "    return FALLBACK_DAYS if value is None else round(value)\n"
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
        # Kept so a checker fix can be re-scored from disk, with no model call. This
        # lab has now mistrusted a checker three times (destructive-git by string
        # match, soft-wrap by rule of thumb, and the patch going empty for every
        # unstaged new file); the patch is the one fact a checker reads that nothing
        # else in the trace captures, so without it a checker fix always costs a full
        # re-run instead of seconds.
        "patch": result.patch,
    }
    check = get_checker(task.checker)(result, **task.checker_args)
    return RunOutcome(outcome=check, trace=trace, **common)
