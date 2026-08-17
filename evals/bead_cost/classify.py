#!/usr/bin/env python3
"""Say what one run's outcome actually was, in the vocabulary the arithmetic needs.

The scorer grades whatever tree it is handed, so an untouched base tree returns the same verdict a
wrong fix does. Those two mean opposite things: one lane produced an answer that is wrong, and the
other produced no answer at all. A third case looks like both and is neither, because the lane was
never reachable. Collapsing them into "failed" is how a lane gets written down as incapable of a
task it was never given.

    ./classify.py <run-dir>        prints one word

    admitted     the canonical verification passed on every criterion
    wrong        the run left a diff and the verification rejected it
    no-diff      the run finished and left the tree at its base commit
    blocked      the run declined to edit, naming a protection the subject requires as unavailable
    aborted      the lane errored out mid-edit and the tree was never scored
    unreachable  the lane could not be reached: rate limit, quota, credentials, unknown model
    truncated    the model's last turn hit its output ceiling and the session ended
    broken       the run never got far enough to produce any of the above
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

# `429` is bounded by non-digits, and that is the whole point of the boundary. Written bare it
# matches the digits INSIDE any number that happens to contain them, and one did: a run's envelope
# carried `"duration_ms":618429`, the classifier read the lane as rate-limited, and a run that had
# simply produced no diff was recorded as one that never reached the model. The two mean opposite
# things - one is a lane that could not be used, the other is an answer the model declined to give -
# and the second is charged to the model while the first rests the lane for a round.
# `usage limit` is codex's own wording for the same condition the other lanes call a quota, and it
# shares none of their vocabulary: a lane exhausted mid-round would otherwise be classified as a
# model that produced nothing, which charges the lane's failure to the model and never rests it.
UNREACHABLE = re.compile(
    r"(?<!\d)429(?!\d)|rate.?limit|quota|usage limit|authentication failed|not logged in"
    r"|no such model|model .* not found",
    re.IGNORECASE,
)


def read_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def last_stop_reason(record: dict | None) -> str | None:
    """The stop reason of the final turn, read from the harness's own log.

    Truncation is invisible in every other artifact: the run exits zero, stdout is empty and the
    tree is untouched, which is indistinguishable from a model that simply declined to act.
    """
    if not record:
        return None
    usage = record.get("usage") or {}
    log = usage.get("session_log")
    if not log or not log.endswith(".jsonl"):
        return None
    stop = None
    try:
        for line in pathlib.Path(log).read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = event.get("message") if isinstance(event, dict) else None
            if isinstance(message, dict) and message.get("stopReason"):
                stop = message["stopReason"]
    except OSError:
        return None
    return stop


# A run is `blocked` when the model itself says it stopped because something the SUBJECT requires
# was not there. Both halves are required and both are read out of the model's own final message -
# never out of tool output, where the repository's documentation would match every pattern below.
#
# The vocabulary is wider than it looks it should be because the models write in the operator's
# language: three refusals on this subject opened with "Blocked by repository safeguards", one with
# "Bloqueado antes de editar", and one with "Não posso iniciar a implementação com segurança". Only
# the last of those carries no word meaning "blocked" at all, which is why the discriminator is the
# PROTECTION being named as missing rather than any particular way of saying no.
BLOCKED_PROTECTION = re.compile(
    r"agent[ _-]?mail|reservation guard|guard de reserva|\bbeads\b|NOT_INITIALIZED|\bbv\b",
    re.IGNORECASE,
)
BLOCKED_UNAVAILABLE = re.compile(
    r"unavailable|not available|not exposed|not installed|missing|cannot|blocked"
    r"|indispon|não est\w* dispon|não dispon|não est\w* instalad|não posso|bloquead",
    re.IGNORECASE,
)


def final_message(run_dir: pathlib.Path, record: dict | None) -> str | None:
    """The last thing the MODEL said, per harness - or None when it cannot be isolated.

    None matters as much as the text. A run whose final message cannot be read is left as whatever
    it already was rather than guessed at: the alternative is scanning the whole of stdout, which is
    how the repository's own documentation came to be read as a lane failing.
    """
    harness = (record or {}).get("harness")
    stdout = run_dir / "stdout.txt"
    if not stdout.exists():
        return None
    text = stdout.read_text(errors="replace")

    if harness == "codex":
        last = None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("{"):
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            item = event.get("item") if isinstance(event.get("item"), dict) else {}
            if item.get("type") == "agent_message" and item.get("text"):
                last = item["text"]
        return last

    # The envelope harnesses put the answer in one object at the end.
    start = text.find("{")
    if start < 0:
        return None
    try:
        envelope = json.loads(text[start:])
    except json.JSONDecodeError:
        return None
    if not isinstance(envelope, dict):
        return None
    for key in ("result", "response", "final_message", "output_text"):
        value = envelope.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def harness_text(run_dir: pathlib.Path, record: dict | None) -> str:
    """The text the HARNESS wrote about itself - never what the agent's tools printed.

    On three of the four lanes stdout is one envelope and the distinction costs nothing. The codex
    lane streams events, and every shell command it runs comes back with its `aggregated_output`
    inside them, so the SUBJECT REPOSITORY'S OWN TEXT lands in the file this scan reads.

    That is not hypothetical. The first codex run on this subject read the repository's AGENTS.md,
    which documents a rate limiter - "Count rate limits per account", "a 429 whose stated delay has
    already elapsed" - and the classifier called the lane unreachable. The lane was fine and the
    model had answered; a lane that could not be used and a model that declined to act mean opposite
    things, and one of them rests the lane for a round.

    So for a stream the scan keeps the harness's own surface: lines that are not events at all
    (whatever a wrapper printed around the run) and events that report an error. The agent's prose
    is left out with the tool output, for the same reason - a model quoting the repository's docs is
    not a lane that ran out of quota.
    """
    text = ""
    try:
        text += (run_dir / "stderr.txt").read_text(errors="replace")
    except OSError:
        pass

    try:
        stdout = (run_dir / "stdout.txt").read_text(errors="replace")
    except OSError:
        return text

    if (record or {}).get("harness") != "codex":
        return text + stdout

    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            text += line + "\n"
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            text += line + "\n"
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        if event.get("type") in ("error", "turn.failed") or item.get("type") == "error":
            text += json.dumps(event) + "\n"
    return text


def classify(run_dir: pathlib.Path) -> str:
    verdict = read_json(run_dir / "verdict.json")
    record = read_json(run_dir / "record.json")

    # What the run PRODUCED is decided before why it might not have, and the order is a correction.
    # Reachability used to be checked first, against the raw streams, which reads any mention of a
    # rate limit as the lane being unusable. A run of 474 turns over 68 minutes that survived a
    # transient 429, committed a fix and scored five of five was classified `unreachable` on that
    # basis, and cost its lane a rest round. A run that produced work was reachable, whatever its
    # logs mention along the way.
    if verdict and verdict.get("scored"):
        section = verdict.get("section_a") or {}
        if section and all(section.values()):
            return "admitted"

    worktree = (record or {}).get("worktree") or {}
    if worktree.get("committed") or worktree.get("dirty"):
        # An edit left behind by a lane that died is not an answer, and `wrong` is the expensive
        # place to put it: cost per completed bead divides by the runs that completed, so a lane
        # failure in the denominator is charged to the model as if it had produced a rejected fix.
        # The distinction is not visible in the tree, which looks the same either way - it is the
        # absence of a verdict beside a harness that reported its own error.
        if not (verdict or {}).get("scored") and ((record or {}).get("usage") or {}).get("status") == "ERROR":
            return "aborted"
        return "wrong"

    # Only now, with nothing produced, does the reason matter.
    if UNREACHABLE.search(harness_text(run_dir, record)):
        return "unreachable"

    if record is not None:
        if last_stop_reason(record) == "length":
            return "truncated"
        if (record.get("usage") or {}).get("status") == "ERROR":
            return "unreachable"
        # Checked last among the no-work cases, and only against the model's own words. A run that
        # declined the task is not a run that attempted it and failed - the subject's AGENTS.md
        # forbids implementing while a coordination protection is down, that protection is not
        # running on this machine, and the arm that reads the rule is the only one it costs. Left as
        # `no-diff` it reads as a model that produced nothing, which is the opposite of what the
        # transcript says happened.
        message = final_message(run_dir, record)
        if message and BLOCKED_PROTECTION.search(message) and BLOCKED_UNAVAILABLE.search(message):
            return "blocked"
        return "no-diff"

    return "broken"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    print(classify(pathlib.Path(sys.argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
