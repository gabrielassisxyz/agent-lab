"""The size of a run's change must include work git was never told about.

A run that solves the bead in a NEW file and never commits leaves every line of it outside
`git diff`. One did: 137 lines in a new file, graded 16/16 on them, recorded as a thirteen-line
change. A column that under-reports only for runs that forget to `git add` does not measure the
solution, it measures the run's git hygiene, and the difference reads as a property of the model.
"""
import pathlib
import subprocess
import tempfile
import unittest

import collect


class WorktreeSize(unittest.TestCase):
    def repo(self) -> pathlib.Path:
        path = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(path)], check=False))
        run = lambda *a: subprocess.run(["git", "-C", str(path), *a], check=True,
                                        capture_output=True, text=True)
        run("init", "-q", "-b", "main")
        run("config", "user.email", "t@example.invalid")
        run("config", "user.name", "t")
        (path / "seed.go").write_text("package main\n")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("branch", "-f", "origin/main")  # stands in for the base ref read_worktree looks for
        return path

    def test_untracked_file_counts_as_added_lines(self):
        path = self.repo()
        (path / "solution.go").write_text("\n".join(f"line {i}" for i in range(137)) + "\n")
        info = collect.read_worktree(path)
        self.assertEqual(info["diff_added"], 137, "a new uncommitted file is the whole change")
        self.assertEqual(info["diff_files"], 1)
        self.assertEqual(info["untracked_files"], 1)

    def test_untracked_adds_to_a_tracked_edit_rather_than_replacing_it(self):
        path = self.repo()
        (path / "seed.go").write_text("package main\n\nfunc extra() {}\n")
        (path / "solution.go").write_text("one\ntwo\n")
        info = collect.read_worktree(path)
        self.assertEqual(info["diff_added"], 4, "two tracked lines plus two untracked ones")
        self.assertEqual(info["diff_files"], 2)

    def test_a_clean_tree_reports_absence_rather_than_zero(self):
        path = self.repo()
        info = collect.read_worktree(path)
        self.assertIsNone(info["diff_added"])
        self.assertIsNone(info["untracked_files"])
        self.assertFalse(info["dirty"])

    def test_a_binary_or_unreadable_untracked_file_does_not_crash_the_record(self):
        path = self.repo()
        (path / "blob.bin").write_bytes(b"\x00\x01\x02\n")
        info = collect.read_worktree(path)
        self.assertEqual(info["untracked_files"], 1)


if __name__ == "__main__":
    unittest.main()
