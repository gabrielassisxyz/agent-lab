"""Record one long session, then reuse it as seeded history for every cell.

The distance axis is measured in turns, and a turn costs an agent call. A cell at
200 turns is 200 invocations to measure the single decision the checker reads; the
199 before it exist only to create distance. Calibrated against real sessions, the
sweep is roughly 54,000 calls, which is not a budget problem but a calendar one: at
that length the model changes underneath the experiment.

The padding turns are identical in every cell. `context.filler_turns` is
deterministic in its seed and asks about the staged repo, not about the task, so a
whole sweep re-drives the same turns over and over. Recording them once and seeding
each cell with the result costs one call per cell instead of N, and the history is
*more* faithful than the alternative: real tool output and the model's own reasoning
rather than inert padding.

**Why cloning the host's transcript rather than fabricating one.** Two other shapes
were considered and rejected. Building a message array against the raw API means the
experiment stops measuring the agent under test and starts measuring the model plus a
bespoke harness, which makes every cell already recorded incomparable. Fabricating
assistant turns is worse than infidelity: authoring the distractor is choosing the
answer, and a fabricated tool_use block would be merged into the agent's commands by
`trajectory.merge_commands` and charged to it as a real violation. Cloning the file
the CLI itself wrote requires no understanding of the format's semantics, only that
the session id is substitutable, which is checked rather than assumed.

**The format is internal and undocumented, so it is verified, not trusted.**
`sanity_check` records a fact, clones the session, and asks for the fact back. It
costs two calls and is meant to run before a sweep: a green exit code alone would
only prove `--resume` accepted the file, while recalling the fact proves the history
actually reached the model's context.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from .agent import Agent, AgentRun

# Line types that mark the start of a real user turn once the tool-result case is
# excluded. A tool result is also recorded as a `user` line, so the two have to be
# told apart by content, not by type.
_USER = "user"


def projects_root() -> Path:
    """Where the host keeps its transcripts. `CLAUDE_CONFIG_DIR` wins when set, which
    is what lets a sweep run against a config dir that is not the operator's own.
    """
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(configured) if configured else Path.home() / ".claude"
    return base / "projects"


def session_file(session_id: str, root: Path | None = None) -> Path:
    """The transcript for a session id.

    Found by globbing rather than by deriving the project slug from the working
    directory. The slug rule is the host's business and has no contract; the session
    id is a uuid and is unique across projects, so a glob cannot pick the wrong file
    and does not break when the slug rule changes.
    """
    root = root or projects_root()
    matches = sorted(root.glob(f"*/{session_id}.jsonl"))
    if not matches:
        raise FileNotFoundError(f"no transcript for session {session_id} under {root}")
    if len(matches) > 1:
        raise RuntimeError(f"session {session_id} matched {len(matches)} transcripts")
    return matches[0]


def read_lines(path: Path) -> list[dict]:
    """Parse a transcript. A line that does not parse is kept out rather than fatal;
    the file is append-only and a torn last line is a normal way for one to end.
    """
    rows = []
    for line in Path(path).read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def is_turn_start(row: dict) -> bool:
    """Whether a line begins a user turn.

    Tool results are recorded as `user` lines too, carrying `tool_result` content
    blocks, and counting them as turns would put a truncation point in the middle of
    an exchange - cutting an assistant's tool call away from its result and leaving
    the seeded history describing work that never completed.
    """
    if row.get("type") != _USER:
        return False
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(isinstance(b, dict) and b.get("type") == "tool_result"
                       for b in content)
    return False


def turn_starts(rows: list[dict]) -> list[int]:
    """Line index of each user turn, in order."""
    return [i for i, row in enumerate(rows) if is_turn_start(row)]


@dataclass(frozen=True)
class Recording:
    """A driven session, kept so cells can be seeded from it.

    `starts` is what makes the axis nested: a shorter point is a literal prefix of a
    longer one, so 1, 20 and 80 turns are three truncations of the same 200-turn
    recording rather than three separate recordings that would each carry their own
    variance.
    """

    session_id: str
    path: Path
    starts: tuple[int, ...]

    @property
    def turns(self) -> int:
        return len(self.starts)


def record(agent: Agent, turns: list[str], repo_dir: Path,
           env: dict[str, str] | None = None, root: Path | None = None) -> Recording:
    """Drive `turns` for real and keep the transcript.

    The agent is the same adapter a cell uses, so a recording is produced by the code
    path being measured rather than by a second implementation that could drift from
    it.
    """
    run: AgentRun = agent.run(turns, repo_dir, env=env)
    if run.error is not None:
        raise RuntimeError(f"recording failed: {run.error}")
    if not run.session_id:
        raise RuntimeError("agent returned no session id; cannot record")

    path = session_file(run.session_id, root)
    starts = turn_starts(read_lines(path))
    if len(starts) < len(turns):
        raise RuntimeError(
            f"transcript has {len(starts)} turns, expected at least {len(turns)}")
    return Recording(session_id=run.session_id, path=path, starts=tuple(starts))


def seed(recording: Recording, turns: int | None = None,
         session_id: str | None = None) -> str:
    """Clone the recording into a fresh session and return its id.

    `turns` keeps that many leading turns and drops the rest, cutting on a turn
    boundary so the kept history never ends mid-exchange. None keeps all of it.

    The clone is what a cell resumes. The original is never opened for writing, so one
    recording seeds a whole sweep: a resumed session appends to its own file, and a
    seed that grew as cells ran would make every later cell longer than the one
    before it.
    """
    rows = read_lines(recording.path)
    if turns is not None:
        if turns < 1:
            raise ValueError(f"a seed needs at least one turn; got {turns}")
        if turns < len(recording.starts):
            rows = rows[:recording.starts[turns]]

    new_id = session_id or str(uuid.uuid4())
    target = recording.path.with_name(f"{new_id}.jsonl")
    if target.exists():
        raise FileExistsError(f"session {new_id} already exists at {target}")

    with target.open("w") as handle:
        for row in rows:
            if row.get("sessionId") == recording.session_id:
                row["sessionId"] = new_id
            handle.write(json.dumps(row) + "\n")
    return new_id


_FACT = "47291"
_PLANT = f"Remember this number for later: {_FACT}. Reply with just: ok"
_RECALL = "What number did I ask you to remember? Reply with digits only."


def sanity_check(agent: Agent, repo_dir: Path, root: Path | None = None) -> None:
    """Prove seeding still works, against the live host. Raises if it does not.

    Two calls: plant a fact in a recorded session, then ask a *clone* to recall it.
    Checking that `--resume` exits zero would only prove the file was accepted; the
    fact coming back is what proves the history reached the model's context. Run this
    before a sweep, because the transcript format has no compatibility contract and a
    host upgrade could change it silently.
    """
    recording = record(agent, [_PLANT], repo_dir, root=root)
    clone = seed(recording)
    run = _resume(agent, clone, _RECALL, repo_dir)
    if run.error is not None:
        raise RuntimeError(f"seeded session failed to resume: {run.error}")
    answer = "".join(e.get("text", "") for e in run.events if e.get("type") == "message")
    if _FACT not in answer:
        raise RuntimeError(
            f"seeded history did not reach the model: asked for {_FACT}, got {answer!r}")


def _resume(agent: Agent, session_id: str, turn: str, repo_dir: Path) -> AgentRun:
    """Drive one turn against an existing session.

    Reaches for the adapter's own resume flag rather than re-implementing the call, so
    an adapter that changes how it resumes changes this too.
    """
    resumed = getattr(agent, "resume_from", None)
    if resumed is None:
        raise RuntimeError(f"{type(agent).__name__} cannot resume a seeded session")
    return resumed(session_id, [turn], repo_dir)
