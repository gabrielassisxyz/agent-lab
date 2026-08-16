#!/usr/bin/env python3
"""Audit one run's implementation against the base, with the toolchain rather than with a model.

Answers the question a passing verdict does not: did this run break something that already worked,
or change a contract nobody asked it to change. Every check here is deterministic - a compiler, a
vetter, a test suite, a set difference over exported symbols - so a finding is a fact and not an
opinion, and nothing needs a second model to confirm it.

Every test file in the repository is restored from the base first. The question is whether the
run's PRODUCTION code still satisfies what already existed, and a run is free to edit tests; grading
against the tests a run shipped would let it move the goalposts and call that a pass.

Runs on a copy. The run's tree is evidence and is never written to.

TWO WAYS THIS REPORTED CONFIDENT NONSENSE BEFORE, both worth knowing because both looked like
results rather than like errors:

  - Auditing the tree a run was LAUNCHED in rather than the one it worked in. The sandbox carries
    the machine's own instruction files, which tell an agent to make its own worktree before its
    first write, and agents follow them. Two runs were reported as having broken every check when
    what had actually been read was an empty checkout. `find-work.sh` exists for exactly this and
    the scorer already used it; this did not.
  - Comparing a run against ITSELF. The base tree here is a copy of the run's own repository moved
    back to the base commit, and a plain `git checkout` REFUSES when the copy carries uncommitted
    changes rather than overwriting them. The refusal is silent, the tree stays at the run's own
    commit, and the API comparison then reports that nothing was removed - by a run that had
    removed six exported methods. The reset is forced for that reason and must stay forced.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

DECL = re.compile(r"^(func|type|var|const) ")
FIND_WORK = pathlib.Path(__file__).parent / "find-work.sh"


def run(cmd: list[str], cwd: pathlib.Path, timeout: int = 600) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def api_surface(tree: pathlib.Path) -> dict[str, set[str]]:
    """Exported declarations per package, read from the toolchain's own view of the package."""
    code, out = run(["go", "list", "./..."], tree)
    surface: dict[str, set[str]] = {}
    if code != 0:
        return surface
    for pkg in out.split():
        if not pkg.startswith("github.com/"):
            continue
        code, doc = run(["go", "doc", "-all", pkg], tree, timeout=120)
        if code != 0:
            continue
        surface[pkg] = {line.rstrip() for line in doc.splitlines() if DECL.match(line)}
    return surface


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_tree", type=pathlib.Path)
    ap.add_argument("run_id")
    ap.add_argument("--run-home", type=pathlib.Path,
                    help="run directory, so the tree the run actually worked in can be discovered")
    ap.add_argument("--base-ref", default="origin/main")
    ap.add_argument("--fixture", type=pathlib.Path,
                    default=pathlib.Path(__file__).parent / "fixtures/llmux_5vg_reservation_test.go")
    ap.add_argument("--fixture-path", default="internal/route/reservation_test.go")
    ap.add_argument("--race-package", default="./internal/route/")
    ap.add_argument("--base-surface", type=pathlib.Path,
                    help="JSON of the base API surface; computed from the base ref when absent")
    args = ap.parse_args()

    report: dict = {"run": args.run_id}

    # A run does not have to work where it was put, and two of them did not: the sandbox carries
    # the machine's own instruction files, which tell an agent to make its own worktree before its
    # first write. Auditing the launch tree of such a run reports a missing implementation as a
    # broken one.
    if args.run_home:
        found = subprocess.run(
            [str(FIND_WORK), str(args.run_tree), str(args.run_home)],
            capture_output=True, text=True)
        if found.returncode == 0 and found.stdout.strip():
            args.run_tree = pathlib.Path(found.stdout.strip())
    report["audited_tree"] = str(args.run_tree)

    graded = pathlib.Path(tempfile.mkdtemp())
    base_tree = pathlib.Path(tempfile.mkdtemp())
    try:
        # symlinks are copied as symlinks and dangling ones tolerated: a run tree carries the
        # jail's own links, and one of them points at a directory that only exists inside it.
        copy = dict(dirs_exist_ok=True, symlinks=True, ignore_dangling_symlinks=True)
        shutil.copytree(args.run_tree, graded, **copy)
        shutil.copytree(args.run_tree, base_tree, **copy)

        # Every test in the repository comes from the base, then the canonical verification on top.
        code, listing = run(["git", "ls-tree", "-r", "--name-only", args.base_ref], args.run_tree)
        tests = [f for f in listing.split() if f.endswith("_test.go")]
        for f in tests:
            code, blob = run(["git", "show", f"{args.base_ref}:{f}"], args.run_tree)
            if code == 0:
                (graded / f).parent.mkdir(parents=True, exist_ok=True)
                (graded / f).write_text(blob)
        shutil.copy(args.fixture, graded / args.fixture_path)
        report["tests_restored"] = len(tests)

        # The base tree: the run's own repository at the base commit, for the API comparison.
        # Forced, and it has to be. The copy inherits whatever the run left uncommitted, and a
        # plain checkout REFUSES rather than overwriting it - leaving the base tree sitting at the
        # run's own commit, so the API comparison silently compares a run against itself and
        # reports that nothing changed.
        run(["git", "reset", "-q", "--hard", args.base_ref], base_tree)
        run(["git", "clean", "-qfd"], base_tree)

        code, out = run(["go", "build", "./..."], graded)
        report["build_ok"] = code == 0
        if code != 0:
            report["build_output"] = out.strip().splitlines()[:12]

        code, out = run(["go", "vet", "./..."], graded)
        report["vet_ok"] = code == 0
        if code != 0:
            report["vet_findings"] = [l for l in out.splitlines() if l.strip()][:20]

        code, out = run(["go", "test", "-count=1", "./..."], graded, timeout=900)
        report["suite_ok"] = code == 0
        failed = sorted({l.split()[1] for l in out.splitlines()
                         if l.startswith("FAIL") and len(l.split()) > 1})
        report["suite_failed_packages"] = failed or None

        code, out = run(["go", "test", "-count=1", "-race", args.race_package], graded, timeout=900)
        report["race_ok"] = code == 0
        if code != 0:
            report["race_output"] = [l for l in out.splitlines() if "DATA RACE" in l or "FAIL" in l][:10]

        base_surface = (json.loads(args.base_surface.read_text()) if args.base_surface
                        else {k: sorted(v) for k, v in api_surface(base_tree).items()})
        run_surface = api_surface(graded)
        removed, added = [], []
        for pkg, decls in base_surface.items():
            present = run_surface.get(pkg, set())
            removed += [f"{pkg}: {d}" for d in sorted(set(decls) - present)]
            added += [f"{pkg}: {d}" for d in sorted(present - set(decls))]
        report["api_removed"] = removed or None
        report["api_added_count"] = len(added) or None
    finally:
        shutil.rmtree(graded, ignore_errors=True)
        shutil.rmtree(base_tree, ignore_errors=True)

    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
