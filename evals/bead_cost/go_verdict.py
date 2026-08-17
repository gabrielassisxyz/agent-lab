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


def merge(run_id: str, contract: dict, legacy: dict) -> dict:
    """One verdict carrying both regimes, with the top level answering "did it solve the bead".

    WHY TWO. The scorer restores the package's whole test surface from the base commit before
    applying the canonical file, so a run that removed a pre-existing public method fails to COMPILE
    - the base helpers still call it - and scores zero before a single canonical assertion runs.
    Zero then means "the older tests do not build", which is not what a reader takes from 0 of 16.

    Measured across this campaign: eight runs across three arms passed all sixteen canonical tests
    on their own tree and were recorded as having solved nothing. One arm's headline moved from 0 of
    5 to 4 of 5 on that difference alone.

    So the two questions are asked apart and both are kept:

      contract                  the canonical file over the tree AS THE RUN LEFT IT. Did the
                                sixteen behaviours get implemented.
      contract_with_legacy_api  the same, with every test file in the package restored from the
                                base. Did they get implemented AND did the pre-existing API survive.

    The top level carries the first, because "completed the bead" is what the cost arithmetic
    divides by. The second is not discarded - it becomes `pre_existing_tests_pass`, which is the
    finding that used to be hidden inside a zero.
    """
    merged = dict(contract)
    merged["run"] = run_id
    merged["pre_existing_tests_pass"] = bool(
        legacy.get("scored") and legacy.get("total") and legacy.get("passed") == legacy.get("total")
    )
    merged["regimes"] = {
        "contract": {key: contract.get(key)
                     for key in ("scored", "section_a", "passed", "total", "build_failed")},
        "contract_with_legacy_api": {key: legacy.get(key)
                                     for key in ("scored", "section_a", "passed", "total",
                                                 "build_failed")},
    }
    return merged


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--merge":
        run_id, contract_path, legacy_path = sys.argv[2], sys.argv[3], sys.argv[4]
        with open(contract_path) as handle:
            contract = json.load(handle)
        with open(legacy_path) as handle:
            legacy = json.load(handle)
        print(json.dumps(merge(run_id, contract, legacy)))
        return 0
    run_id = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    expected = sys.argv[2:] or None
    print(json.dumps(verdict(run_id, read_results(sys.stdin), expected)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
