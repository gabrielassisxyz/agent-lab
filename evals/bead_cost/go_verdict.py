#!/usr/bin/env python3
"""Reduce `go test -json` to one run's verdict.

Graded rather than binary, because the bead's canonical verification carries sixteen test functions
and a run that implements reservation but not release-once is a different result from one that
implements neither. A binary verdict would put both on the floor and measure nothing, which is the
saturation the first subject's metrics already demonstrated.

A test that never reports a terminal action - the package failed to build, or the run was cut off
mid-suite - leaves NO entry rather than a false one. An absent result and a failing result mean
opposite things about the tree, and the caller distinguishes them by the empty report.
"""

import json
import sys

TERMINAL = ("pass", "fail", "skip")


def read_results(lines) -> dict[str, str]:
    """Last terminal action per test wins: Go reports a subtest's parent after its children."""
    results: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # `go test -json` interleaves plain build errors with the JSON stream, and a build
            # error is exactly the case that must not look like a parse bug.
            continue
        test, action = event.get("Test"), event.get("Action")
        if isinstance(test, str) and action in TERMINAL:
            results[test] = action
    return results


def verdict(run_id: str, results: dict[str, str], expected: list[str] | None = None) -> dict:
    """Grade against the tests the canonical verification is KNOWN to carry, not against the ones
    that happened to report.

    Which matters here in a way it did not for the first subject, because this bead's base tree does
    not compile: the verification is already in it, naming a contract nothing implements yet. So a
    build failure is the ordinary starting state and the ordinary shape of a near-miss - a solution
    that works but names its type something else fails to build exactly like one that was never
    written. Reporting that as an unscored run would price both as a broken harness and quietly
    remove the hardest cases from the denominator.

    A build failure is therefore all criteria false, flagged so it stays legible. `scored: False` is
    kept for the case it was meant for: the suite could not be run at all.
    """
    if expected is None:
        expected = sorted(results)
    if not expected:
        return {
            "run": run_id,
            "scored": False,
            "reason": "no expected tests given and none reported - the suite did not run",
        }
    section_a = {name: results.get(name) == "pass" for name in sorted(expected)}
    return {
        "run": run_id,
        "scored": True,
        "section_a": section_a,
        "passed": sum(section_a.values()),
        "total": len(section_a),
        "build_failed": not results,
    }


def main() -> int:
    run_id = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    expected = sys.argv[2:] or None
    print(json.dumps(verdict(run_id, read_results(sys.stdin), expected)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
