"""No `... | grep -q` inside a script that sets `pipefail`.

The bug this exists to keep out is silent and it reverses the answer. `grep -q` exits the moment it
matches; the process on the left still has the rest of its output to write, takes SIGPIPE, and the
pipeline reports 141. Under `pipefail` that reads as failure, so `if writer | grep -q pattern` takes
the else branch **because the pattern was found**.

It is not theoretical and it is not rare. Measured on this repo's own sandbox gate, against a
sandbox whose model demonstrably worked: 4 false rejections in 10 runs, from a 36 KB catalogue whose
match sits on line 17. It fires more often on a loaded machine, so for weeks it presented as
contention between concurrent runs and cost nine of them, plus two rewrites of the npm cache layout
that fixed nothing because npm was never involved.

Replace the pipeline with a match that has no writer to kill: `[[ "$text" == *"$pat"* ]]` for a
fixed string, `grep -q … <<< "$text"` for a regex, `[ -n "$(cmd)" ]` for existence.

A pipeline that genuinely cannot be affected - one running in a fresh shell that does not inherit
pipefail, for instance - carries `pipefail-safe` in a comment on the line or just above it.
"""

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPE_TO_QUIET_GREP = re.compile(r"\|\s*(command\s+)?grep\s+-[a-zA-Z]*q")
SETS_PIPEFAIL = re.compile(r"^\s*set\s+-[a-zA-Z]*o?\s*.*pipefail", re.MULTILINE)
EXEMPT = "pipefail-safe"


def tracked_shell_files():
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    for name in out.split("\0"):
        if not name:
            continue
        path = ROOT / name
        if path.suffix == ".sh" or path.parent.name == "bin":
            if path.is_file():
                yield path


class PipefailGrepQ(unittest.TestCase):
    def test_no_pipe_into_quiet_grep_under_pipefail(self):
        offenders = []
        for path in tracked_shell_files():
            text = path.read_text(errors="ignore")
            if not SETS_PIPEFAIL.search(text):
                continue
            lines = text.splitlines()
            for number, line in enumerate(lines, start=1):
                # A comment describing the defect is not the defect - and this file's own fixes are
                # commented with the pattern they replaced.
                if line.lstrip().startswith("#"):
                    continue
                if not PIPE_TO_QUIET_GREP.search(line):
                    continue
                # The exemption is looked for in the comment block above, not only on the line
                # before it: a reason worth writing rarely fits on one line.
                preceding = lines[max(0, number - 4) : number]
                if any(EXEMPT in candidate for candidate in preceding):
                    continue
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
        self.assertEqual(
            [],
            offenders,
            "a quiet grep on the right of a pipe inverts its own answer under pipefail:\n"
            + "\n".join(offenders),
        )

    def test_the_defect_is_real(self):
        """Guards the guard: if this ever passes, SIGPIPE no longer reaches the writer and the
        rule above has become superstition rather than a rule."""
        script = (
            "set -euo pipefail\n"
            'big=$(seq 1 200000)\n'
            'if printf "%s\\n" "$big" | grep -qF 1; then echo found; else echo missed; fi\n'
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, check=True
        )
        self.assertEqual("missed", result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
