"""Tests for recording a session once and seeding cells from it.

The live call is not exercised here (that is `sanity_check`, run against the real
host before a sweep). What is covered is everything that decides whether a seeded
cell is a faithful copy of the recording: which lines count as turn boundaries,
that truncation lands on one, that the clone is independent of its source, and that
the id substitution is complete. A mistake in any of those is silent - the cell runs,
the checker scores it, and the number is wrong.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from .agent import AgentRun
from .recording import (Recording, is_turn_start, read_lines, record, seed,
                        session_file, turn_starts)

SID = "11111111-1111-1111-1111-111111111111"


def _user(text):
    return {"type": "user", "sessionId": SID, "message": {"role": "user", "content": text}}


def _tool_result(tool_id="t1"):
    # A tool result is also a `user` line. Telling it apart from a turn is the whole
    # job of `is_turn_start`.
    return {"type": "user", "sessionId": SID, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}]}}


def _assistant(text="fine"):
    return {"type": "assistant", "sessionId": SID,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _meta(kind="mode"):
    return {"type": kind, "sessionId": SID}


def _transcript():
    """Three user turns, each answered, with a tool exchange inside the second."""
    return [
        _meta("last-prompt"), _meta("mode"),
        _user("turn zero"), _assistant("ack"),                       # turn 0
        _user("turn one"), _assistant("calling a tool"),
        _tool_result(), _assistant("done"),                          # turn 1
        _user("turn two"), _assistant("finished"),                   # turn 2
    ]


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


class FakeResumableAgent:
    """Returns a fixed session id and records what it was asked to drive."""

    def __init__(self, session_id=SID):
        self.session_id = session_id
        self.driven: list[tuple[str | None, list[str]]] = []

    def run(self, turns, repo_dir, env=None, session_id=None):
        self.driven.append((session_id, list(turns)))
        return AgentRun(session_id=self.session_id)

    def resume_from(self, session_id, turns, repo_dir, env=None):
        return self.run(turns, repo_dir, env=env, session_id=session_id)


class TestTurnBoundaries(unittest.TestCase):
    def test_a_string_prompt_starts_a_turn(self):
        self.assertTrue(is_turn_start(_user("hello")))

    def test_a_tool_result_is_not_a_turn(self):
        # It is a `user` line like any prompt, and counting it would place a cut in
        # the middle of an exchange.
        self.assertFalse(is_turn_start(_tool_result()))

    def test_an_assistant_line_is_not_a_turn(self):
        self.assertFalse(is_turn_start(_assistant()))

    def test_metadata_lines_are_not_turns(self):
        for kind in ("mode", "last-prompt", "permission-mode", "attachment"):
            self.assertFalse(is_turn_start(_meta(kind)), kind)

    def test_boundaries_are_found_in_order(self):
        self.assertEqual(turn_starts(_transcript()), [2, 4, 8])


class TestSeed(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        rows = _transcript()
        path = _write(self.dir / f"{SID}.jsonl", rows)
        self.recording = Recording(session_id=SID, path=path,
                                   starts=tuple(turn_starts(rows)))

    def test_a_full_seed_copies_every_line(self):
        new_id = seed(self.recording)
        rows = read_lines(self.recording.path.with_name(f"{new_id}.jsonl"))
        self.assertEqual(len(rows), len(_transcript()))

    def test_the_session_id_is_rewritten_everywhere(self):
        # A single missed line would leave the clone pointing at its source, and the
        # two sessions would then append to each other.
        new_id = seed(self.recording)
        rows = read_lines(self.recording.path.with_name(f"{new_id}.jsonl"))
        self.assertTrue(all(r["sessionId"] == new_id for r in rows))
        self.assertFalse(any(SID in json.dumps(r) for r in rows))

    def test_truncation_cuts_on_a_turn_boundary(self):
        new_id = seed(self.recording, turns=2)
        rows = read_lines(self.recording.path.with_name(f"{new_id}.jsonl"))
        self.assertEqual(len(turn_starts(rows)), 2)
        # The kept history ends with the second turn fully answered, not mid-exchange.
        self.assertEqual(rows[-1]["type"], "assistant")

    def test_a_shorter_seed_is_a_prefix_of_a_longer_one(self):
        # This is what makes the distance axis nested: the points share one history
        # instead of each carrying its own.
        short = read_lines(self.recording.path.with_name(
            f"{seed(self.recording, turns=1)}.jsonl"))
        long = read_lines(self.recording.path.with_name(
            f"{seed(self.recording, turns=3)}.jsonl"))
        strip = lambda rows: [{k: v for k, v in r.items() if k != "sessionId"} for r in rows]
        self.assertEqual(strip(short), strip(long)[:len(short)])

    def test_asking_for_more_turns_than_exist_keeps_the_whole_recording(self):
        new_id = seed(self.recording, turns=99)
        rows = read_lines(self.recording.path.with_name(f"{new_id}.jsonl"))
        self.assertEqual(len(rows), len(_transcript()))

    def test_the_source_recording_is_never_written_to(self):
        # One recording seeds a whole sweep. If seeding grew the source, every later
        # cell would carry more history than the one before it.
        before = self.recording.path.read_text()
        seed(self.recording, turns=1)
        seed(self.recording, turns=2)
        self.assertEqual(self.recording.path.read_text(), before)

    def test_two_seeds_do_not_collide(self):
        self.assertNotEqual(seed(self.recording), seed(self.recording))

    def test_seeding_onto_an_existing_session_refuses(self):
        taken = seed(self.recording)
        with self.assertRaises(FileExistsError):
            seed(self.recording, session_id=taken)

    def test_a_zero_turn_seed_is_refused(self):
        with self.assertRaises(ValueError):
            seed(self.recording, turns=0)


class TestSessionFile(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_a_transcript_is_found_under_any_project_slug(self):
        # The slug is derived from the working directory by the host and has no
        # contract, so the lookup globs on the id instead of rebuilding the rule.
        project = self.root / "-some-odd--slug-the-host-chose"
        project.mkdir()
        _write(project / f"{SID}.jsonl", [_user("hi")])
        self.assertEqual(session_file(SID, self.root).parent, project)

    def test_a_missing_transcript_raises(self):
        with self.assertRaises(FileNotFoundError):
            session_file(SID, self.root)

    def test_an_ambiguous_id_raises_rather_than_guessing(self):
        for name in ("project-a", "project-b"):
            (self.root / name).mkdir()
            _write(self.root / name / f"{SID}.jsonl", [_user("hi")])
        with self.assertRaises(RuntimeError):
            session_file(SID, self.root)


class TestRecord(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        (self.root / "proj").mkdir()

    def _plant(self, rows):
        return _write(self.root / "proj" / f"{SID}.jsonl", rows)

    def test_recording_locates_the_transcript_and_its_turns(self):
        self._plant(_transcript())
        found = record(FakeResumableAgent(), ["a", "b", "c"], Path("/repo"), root=self.root)
        self.assertEqual(found.session_id, SID)
        self.assertEqual(found.starts, (2, 4, 8))
        self.assertEqual(found.turns, 3)

    def test_a_failed_run_raises_instead_of_recording(self):
        class Failing(FakeResumableAgent):
            def run(self, turns, repo_dir, env=None, session_id=None):
                return AgentRun(error="exit 1 on turn 0")

        with self.assertRaises(RuntimeError):
            record(Failing(), ["a"], Path("/repo"), root=self.root)

    def test_a_short_transcript_raises(self):
        # Fewer turns on disk than were driven means the recording is not what the
        # caller asked for, and seeding from it would silently under-shoot the axis.
        self._plant(_transcript())
        with self.assertRaises(RuntimeError):
            record(FakeResumableAgent(), ["a"] * 5, Path("/repo"), root=self.root)


if __name__ == "__main__":
    unittest.main()
