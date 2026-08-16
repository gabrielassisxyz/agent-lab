#!/usr/bin/env python3
"""Scan one tree with UBS and the Go analysers, reporting only what the base does not already say.

A scan without a baseline is not a measurement of the run. The base commit of the current subject
alone carries hundreds of findings; attributing those to whichever model happened to be scanned
next is the exact mistake this experiment exists to avoid. Run this against the base first, keep
the result, and pass it as `--baseline` for every implementation after.

Findings are keyed on (tool, rule, file, snippet-or-message) and NOT on line number. A run that
adds a function shifts every line below it, and keying on position reports the whole file as new.

PRODUCTION AND TEST FINDINGS ARE COUNTED SEPARATELY, and the reason is an incentive rather than a
technicality. Test files a run wrote are work it did and are not discarded - but a run that writes
MORE tests then collects more findings, so a single total reads "wrote extra tests" as "introduced
more problems". One run authored a 100-line crash test and drew thirteen findings for it while
runs that wrote no extra tests drew none. Two columns keep both facts without letting one masquerade
as the other.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys

LINE = re.compile(r"^(?P<file>[^:\s]+\.go):\d+:\d+:?\s*(?P<msg>.*)$")


def run(cmd, cwd, timeout=900, merge_stderr=True):
    """Run a tool. `merge_stderr` is FALSE for anything whose output is parsed as JSON.

    UBS writes progress lines to stderr, and concatenating them onto its SARIF made the document
    unparseable - so the reader returned an empty set and the tool silently contributed nothing.
    It was caught only by comparing against an earlier baseline, where the same scan had produced
    335 findings. A parser that yields zero on malformed input is indistinguishable from a clean
    tree, which is the failure shape this repository keeps paying for.
    """
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 124, ""
    out = p.stdout or ""
    return p.returncode, out + (p.stderr or "") if merge_stderr else out


def ubs_findings(tree: pathlib.Path) -> set[tuple]:
    _, out = run(["ubs", ".", "--only=golang", "--format=sarif"], tree, merge_stderr=False)
    try:
        doc = json.loads(out[out.find("{"):])
    except (json.JSONDecodeError, ValueError):
        return set()
    found = set()
    for r in doc.get("runs", [{}])[0].get("results", []):
        loc = (r.get("locations") or [{}])[0].get("physicalLocation", {})
        uri = loc.get("artifactLocation", {}).get("uri", "")
        rel = uri.split(str(tree), 1)[-1].lstrip("/") if str(tree) in uri else uri
        snippet = (loc.get("region", {}).get("snippet") or {}).get("text", "").strip()
        found.add(("ubs", r.get("ruleId", ""), rel,
                   snippet or r.get("message", {}).get("text", "")[:80]))
    return found


def line_tool(tree: pathlib.Path, tool: str, cmd: list[str]) -> set[tuple]:
    _, out = run(cmd, tree)
    found = set()
    for line in out.splitlines():
        m = LINE.match(line.strip())
        if m:
            found.add((tool, "", m.group("file"), m.group("msg")))
    return found


def gosec_findings(tree: pathlib.Path) -> set[tuple]:
    _, out = run(["gosec", "-quiet", "-fmt=json", "./..."], tree, merge_stderr=False)
    try:
        doc = json.loads(out[out.find("{"):])
    except (json.JSONDecodeError, ValueError):
        return set()
    found = set()
    for i in doc.get("Issues", []):
        rel = i.get("file", "").split(str(tree), 1)[-1].lstrip("/")
        found.add(("gosec", i.get("rule_id", ""), rel, (i.get("code") or "").strip()[:120]))
    return found


def govulncheck_findings(tree: pathlib.Path) -> set[tuple]:
    """Vulnerable dependencies. The only tool here that would notice a run editing `go.mod`."""
    _, out = run(["govulncheck", "-format=json", "./..."], tree, merge_stderr=False)
    found = set()
    # The stream is pretty-printed objects rather than one per line, so decode incrementally and
    # skip whatever is not an object: a bare string decodes happily and then has no `.get`.
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(out):
        try:
            event, end = decoder.raw_decode(out, idx)
        except ValueError:
            idx += 1
            continue
        idx = end
        if not isinstance(event, dict):
            continue
        finding = event.get("finding")
        if isinstance(finding, dict):
            found.add(("govulncheck", finding.get("osv", ""), "go.mod",
                       str(finding.get("fixed_version") or "")))
    return found


def scan(tree: pathlib.Path) -> set[tuple]:
    found = set()
    found |= ubs_findings(tree)
    found |= line_tool(tree, "staticcheck", ["staticcheck", "./..."])
    # `-ignoretests` is required, not cosmetic. errcheck type-checks each package INCLUDING its
    # tests, and this subject's base has a package whose test does not compile by construction -
    # that failing test IS how the bead states its contract. Without the flag errcheck aborts the
    # whole run and contributes nothing, which an aggregator reads as "nothing to report" rather
    # than as "did not run". With it, the base and the reference solution both report zero.
    found |= line_tool(tree, "errcheck", ["errcheck", "-ignoretests", "./..."])
    found |= line_tool(tree, "golangci-lint", ["golangci-lint", "run", "--output.text.path=stdout", "./..."])
    found |= gosec_findings(tree)
    found |= govulncheck_findings(tree)
    return found


def is_test(rel: str) -> bool:
    return rel.endswith("_test.go")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree", type=pathlib.Path)
    ap.add_argument("label")
    ap.add_argument("--baseline", type=pathlib.Path)
    args = ap.parse_args()

    found = scan(args.tree.resolve())
    if not args.baseline:
        json.dump({"label": args.label, "findings": sorted(found)}, sys.stdout)
        print()
        return 0

    base = {tuple(x) for x in json.loads(args.baseline.read_text())["findings"]}
    new = sorted(found - base)
    production = [f for f in new if not is_test(f[2])]
    tests = [f for f in new if is_test(f[2])]

    def by_tool(rows):
        counts: dict[str, int] = {}
        for tool, *_ in rows:
            counts[tool] = counts.get(tool, 0) + 1
        return counts

    json.dump({
        "label": args.label,
        "new_in_production": len(production),
        "new_in_run_authored_tests": len(tests),
        "production_by_tool": by_tool(production),
        "tests_by_tool": by_tool(tests),
        "removed_from_baseline": len(base - found),
        "production": production[:60],
        "tests": tests[:20],
    }, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
