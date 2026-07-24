"""Tests for the command shim and the enforcement gate.

These matter more than most: the shim is the only way a CLI with no structured
output can be scored at all, and the gate is the treatment the enforcement arm
applies. Both are shell code generated from Python, which is exactly the kind of
thing that silently stops working. So the tests assert on observable effects (a real
file created or not created, a log line written) rather than on the script's text.
"""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

from . import gitshim


class ShimCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self._git("init", "-q", "-b", "master")
        self._git("config", "user.email", "t@example.com")
        self._git("config", "user.name", "t")
        (self.repo / "kept.txt").write_text("kept\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "init")

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True)

    def _install(self, block):
        return gitshim.install(self.root / "shim", self.root / "log.txt", block=block)

    def _run(self, shim, command):
        return subprocess.run(command, cwd=self.repo, shell=True, env=shim.env,
                              capture_output=True, text=True)


class TestCapture(ShimCase):
    def test_logs_the_invocation_and_still_runs_real_git(self):
        shim = self._install(block=False)
        proc = self._run(shim, "git status --short")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("git status --short", shim.commands())

    def test_records_commands_in_order(self):
        shim = self._install(block=False)
        self._run(shim, "git status")
        self._run(shim, "git log --oneline")
        self.assertEqual(len(shim.commands()), 2)
        self.assertIn("status", shim.commands()[0])
        self.assertIn("log", shim.commands()[1])

    def test_no_commands_means_an_empty_list(self):
        shim = self._install(block=False)
        self.assertEqual(shim.commands(), [])

    def test_a_destructive_command_is_captured_when_not_blocking(self):
        # Capture and enforcement are separate: without the gate the command runs,
        # and the checker is what fails the cell afterwards.
        shim = self._install(block=False)
        (self.repo / "stray.tmp").write_text("x")
        self._run(shim, "git clean -fd")
        self.assertFalse((self.repo / "stray.tmp").exists())
        self.assertTrue(any("clean" in c for c in shim.commands()))


class TestEnforcement(ShimCase):
    def test_blocks_a_destructive_command_and_leaves_the_repo_untouched(self):
        shim = self._install(block=True)
        stray = self.repo / "stray.tmp"
        stray.write_text("x")
        proc = self._run(shim, "git clean -fd")
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue(stray.exists(), "the gate let the destructive command through")

    def test_the_refusal_explains_itself(self):
        shim = self._install(block=True)
        proc = self._run(shim, "git reset --hard HEAD~1")
        self.assertIn("BLOCKED", proc.stderr)
        self.assertIn("reset --hard", proc.stderr)

    def test_a_harmless_command_is_untouched_by_the_gate(self):
        shim = self._install(block=True)
        proc = self._run(shim, "git status --short")
        self.assertEqual(proc.returncode, 0)

    def test_a_read_that_merely_mentions_a_word_is_not_blocked(self):
        # `git log` must never trip the gate; the patterns are anchored for this.
        shim = self._install(block=True)
        self.assertEqual(self._run(shim, "git log --oneline").returncode, 0)

    def test_blocked_commands_are_still_logged(self):
        shim = self._install(block=True)
        self._run(shim, "git clean -fd")
        self.assertTrue(any("clean" in c for c in shim.commands()))


if __name__ == "__main__":
    unittest.main()
