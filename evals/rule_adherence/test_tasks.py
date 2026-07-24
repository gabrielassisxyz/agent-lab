"""Tests for the task-set itself.

A task file is data, and data that is never executed rots quietly. The staging
snippet of each task is real shell run inside a real git repo, so a quoting mistake
in it does not surface until a live run is already burning model time on a cell that
cannot even start. These tests run every setup against the actual runner fixture,
which is cheap and deterministic, and they check the design rules the first sweep
taught rather than only the schema.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile
import unittest

from .checkers import REGISTRY
from .placements import load_corpus, relevant_rules
from .runner import _init_repo
from .schema import load_tasks

_HERE = pathlib.Path(__file__).parent
_TASKS = load_tasks(_HERE / "tasks.json")
_CORPUS = load_corpus(_HERE / "corpus.sample.json")


class TestTaskSetShape(unittest.TestCase):
    def test_every_task_references_a_real_checker(self):
        for task in _TASKS:
            self.assertIn(task.checker, REGISTRY, task.id)

    def test_every_task_references_a_rule_in_the_corpus(self):
        known = {rule.id for rule in _CORPUS}
        for task in _TASKS:
            self.assertIn(task.rule_id, known, task.id)

    def test_every_task_category_retrieves_at_least_one_rule(self):
        # The just-in-time placements select rules by the task's category. A task
        # whose category matches nothing would silently compose an empty tail, so
        # its arm would be the control wearing another arm's name.
        for task in _TASKS:
            self.assertTrue(relevant_rules(task.category, _CORPUS), task.id)

    def test_every_corpus_category_is_exercised_by_some_task(self):
        covered = {task.category for task in _TASKS}
        for rule in _CORPUS:
            self.assertIn(rule.category, covered, rule.id)


class TestTaskSetup(unittest.TestCase):
    """Every staging snippet has to actually run."""

    def test_each_setup_runs_in_a_fixture_repo(self):
        for task in _TASKS:
            if not task.setup:
                continue
            with self.subTest(task=task.id), tempfile.TemporaryDirectory() as tmp:
                repo = pathlib.Path(tmp) / "repo"
                _init_repo(repo)
                proc = subprocess.run(task.setup, cwd=repo, shell=True,
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0,
                                 f"{task.id} setup failed: {proc.stderr}")

    def test_the_unmerged_branch_task_really_stages_an_unmerged_branch(self):
        # The whole point of that task is that `git branch -d` refuses, so the
        # destructive `-D` becomes the tempting way out. If the branch were merged
        # the safe command would work and the task would tempt nothing.
        task = next(t for t in _TASKS if t.id == "safety-delete-unmerged-branch")
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / "repo"
            _init_repo(repo)
            subprocess.run(task.setup, cwd=repo, shell=True, check=True, capture_output=True)
            safe = subprocess.run(["git", "branch", "-d", "feature/half-done"],
                                  cwd=repo, capture_output=True, text=True)
            self.assertNotEqual(safe.returncode, 0, "the safe delete succeeded; nothing tempts")

    def test_the_tool_use_task_really_installs_a_working_tool(self):
        task = next(t for t in _TASKS if t.id == "tool-log-cache-ttl")
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / "repo"
            _init_repo(repo)
            subprocess.run(task.setup, cwd=repo, shell=True, check=True, capture_output=True)
            subprocess.run("./bin/oplog 'ttl raised to 3600'", cwd=repo, shell=True,
                           check=True, capture_output=True)
            self.assertIn("ttl raised to 3600", (repo / "ops" / "log.md").read_text())


class TestTaskDesignRules(unittest.TestCase):
    """The two rules the first sweep taught, enforced on the data."""

    def test_an_instruction_never_states_the_rule_it_tests(self):
        # The old branch task said "Follow the repo's branching convention", which
        # hands over the very thing the rule was supposed to supply. A task that
        # states its own rule measures reading comprehension, not adherence.
        leaks = re.compile(
            r"\bconvention|\bconventional\b|commit message format|"
            r"in english|co-authored|branch naming", re.IGNORECASE)
        for task in _TASKS:
            with self.subTest(task=task.id):
                self.assertIsNone(leaks.search(task.instruction),
                                  f"{task.id} states its own rule: {task.instruction!r}")

    def test_language_tasks_are_written_in_the_language_they_test_against(self):
        # These pair a request in Portuguese with a rule saying file content is
        # always English, so the request itself must not be English or the model has
        # nothing to be tempted by. Task instructions are stimulus data, which is the
        # one place in this repo where non-English text is the content.
        portuguese = re.compile(r"\b(adicione|explicando|projeto|uma|que|deste|qual)\b",
                                re.IGNORECASE)
        for task in _TASKS:
            if task.category != "format-language":
                continue
            with self.subTest(task=task.id):
                self.assertTrue(portuguese.search(task.instruction), task.id)

    def test_task_ids_are_prefixed_by_their_category(self):
        prefixes = {
            "safety-critical": "safety-", "non-standard-conventions": ("conv-",),
            "attribution": "attr-", "format-language": "lang-",
            "tool-use": "tool-", "doc-consultation": "doc-",
        }
        for task in _TASKS:
            expected = prefixes[task.category]
            self.assertTrue(task.id.startswith(expected), task.id)


if __name__ == "__main__":
    unittest.main()
