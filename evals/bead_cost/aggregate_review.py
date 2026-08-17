#!/usr/bin/env python3
"""Decode and aggregate the qualitative review, by a rule fixed before any answer existed.

THAT ORDERING IS THE POINT. An aggregation chosen after reading the answers is a choice made while
already knowing the result, and a number produced that way is not a measurement. Everything this
file decides - mean rank rather than majority vote, corroborated versus single-source, what counts
as the review having failed - was settled in the plan and is implemented here before the first
reviewer was called.

WHAT IT REPORTS

  - the ranking, by MEAN RANK across reviewers (Borda). The task is an ordering, and majority voting
    over orderings throws away exactly what makes an ordering useful.
  - whether the reviewers agree with each other at all, as pairwise Spearman correlation. Four
    orderings that scatter mean the metric has no signal, however well the prose reads.
  - where the REFERENCE implementation landed. It is NOT a control, and the difference matters:
    that commit was produced the same way the candidates were, by an agent working on a repository
    where dozens of commits landed the same day, and nothing but having been merged marks it as
    good. So its position falsifies nothing. Last is a result worth reading - the merged
    implementation may genuinely cost more later than four candidates - and first is not evidence
    of signal either. It is reported loudly and it does not decide validity.
  - self-preference: whether a reviewer placed its own family's implementation above where the
    conflict-free reviewers placed it.
  - findings from pass A, marked corroborated (both reviewers raised it) or single-source.

The verdict on validity is printed as a verdict, not left for a reader to infer politely.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from itertools import combinations

CONFLICT_FREE = {"codex", "glm"}
# Which reviewer shares a family with which lane. Recorded here rather than inferred, because the
# whole point is to test the assumption rather than to encode it silently.
SAME_FAMILY = {"opus": "sonnet", "gemini": "gemini-3.7-flash"}


def unwrap_envelope(value: dict) -> dict:
    """Take the review out of `agy`'s reply envelope, which is a dict but not the answer.

    Only `agy` is handed a schema, and what it returns is `{"status": ..., "response": ...,
    "structured_output": ...}` with the answer inside one of the last two. Read as-is it is a
    perfectly valid dict with no `ranking` key, so the reviewer is dropped for having answered
    correctly - a whole reviewer missing from the panel and nothing anywhere saying why.

    Which half holds it is not fixed: the same CLI has put the full answer in `response` while
    `structured_output` held an acknowledgement, and the reverse. So both are tried and the one
    that carries the expected keys wins.
    """
    if "status" not in value:
        return value
    for candidate in (value.get("structured_output"), value.get("response")):
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, str) and candidate.strip():
            try:
                parsed = json.loads(candidate)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return value


def json_objects(text: str):
    """Yield the JSON objects in a reviewer's output, LAST one first.

    SCANNING FORWARDS DOES NOT WORK HERE, and the obvious brace counter is the trap. `codex exec`
    echoes the whole prompt before answering, the prompt carries the packet, and the packet is Go
    source - braces and quotes of its own, in quantity. A counter walking from the start loses
    synchronisation inside that code and never reaches the answer: on a real 38 KB transcript it
    produced two candidate spans, neither of them parseable, out of a file that ends in a perfectly
    well-formed object.

    `raw_decode` removes the guesswork. It parses a value starting at a given offset and simply
    stops when the value ends, so nothing has to be known about what follows - no closing brace to
    find, no code to survive. Walking the opening braces from the end backwards therefore reaches
    the answer before anything upstream of it, which is what makes the echoed example harmless.
    """
    decoder = json.JSONDecoder()
    for index in range(len(text) - 1, -1, -1):
        if text[index] != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, index)
        except ValueError:
            continue
        if isinstance(value, dict):
            yield value


def first_object(text: str) -> dict | None:
    """The first parseable object in the text, which is where an `agy` reply envelope will be."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, index)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def load_json(text: str, *expected: str) -> dict | None:
    """Pull the reviewer's answer out of whatever its CLI wrote around it.

    Only `agy` can be handed a schema; the rest are asked in the prompt and answer inside whatever
    their harness prints. A reviewer that answered correctly inside a transcript has still answered,
    and dropping it would silently shrink the panel.

    THE SEARCH RUNS BACKWARDS, and the expected key is what stops it. Reading from the first brace
    onwards produced nothing usable for seven calls out of eighteen, and the reviewers that wrote
    them would have been dropped for having answered. Two things upstream of the answer parse
    perfectly well on their own - the objects nested inside it, and the example in the echoed prompt
    - so "the last object" is not enough on its own: `reasons[0]` is the last object in the file and
    it is not the answer. Naming the key the caller needs is what distinguishes them.
    """
    # THE TWO SHAPES WANT OPPOSITE RULES, which is why the envelope is settled first and alone.
    # An `agy` file is one object and nothing else, and it carries a copy of the schema it was
    # handed - whose `properties` is an object whose KEYS are the very keys named below. Search that
    # file backwards and the schema is reached before the answer, so the reviewer comes back holding
    # {"type": "string"} where its ranking should be. Once a reply envelope is recognised, it is the
    # only thing in the file worth reading.
    envelope = first_object(text)
    if envelope is not None and "status" in envelope:
        answer = unwrap_envelope(envelope)
        return answer if answer is not envelope else None

    fallback = None
    for value in json_objects(text):
        if expected and any(key in value for key in expected):
            return value
        if fallback is None:
            fallback = value
    return fallback


REFUSALS = {"NONE", "CANNOT_TELL", "CANNOT TELL", "UNKNOWN", ""}


def read_blinding_pick(value, mapping: dict) -> tuple[str, str]:
    """Read the blinding answer as a letter, a refusal, or something nobody should guess at.

    Returns (letter, unreadable). Exactly one is ever non-empty.

    THE PROMPT OFFERS REFUSALS AND MEANS IT - "none" and "cannot_tell" are listed beside the letters
    because they are the useful answers when they are the true ones. Taking the first character of
    the reply turns "cannot_tell" into "C", and C, in the first real run, was the entry belonging to
    Gemini's own family. Three of four reviewers refused, and the check reported the blinding broken
    and the whole ranking void. Opus refused too and escaped only because its family happened to be
    the B entry.

    So a pick is an exact letter and nothing else. Anything unrecognised is neither accepted nor
    silently dropped: swallowing it is how a real blinding failure goes unnoticed, which is the
    failure this check exists to catch.
    """
    text = str(value if value is not None else "").strip().strip('"').upper()
    if text in REFUSALS:
        return "", ""
    if text in mapping:
        return text, ""
    return "", text


def spearman(a: list[str], b: list[str]) -> float | None:
    shared = [x for x in a if x in b]
    if len(shared) < 3:
        return None
    ra = {x: a.index(x) for x in shared}
    rb = {x: b.index(x) for x in shared}
    n = len(shared)
    d2 = sum((ra[x] - rb[x]) ** 2 for x in shared)
    return 1 - (6 * d2) / (n * (n * n - 1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("answers", type=pathlib.Path)
    ap.add_argument("--key", type=pathlib.Path, required=True,
                    help="the KEY written beside the packet and kept out of the jail")
    args = ap.parse_args()

    key = json.loads(args.key.read_text())
    mapping = key["mapping"]
    reference = key["reference_letter"]

    rankings: dict[str, list[str]] = {}
    # A reviewer whose answer is unusable is dropped from every number below, and a report that
    # mentions it only on stderr reads exactly like a complete panel. So the omission is carried to
    # the verdict instead: an ordering averaged over three reviewers is a different measurement from
    # one averaged over four, and the difference has to be visible where the result is.
    unusable_b: list[str] = []
    for path in sorted(args.answers.glob("passB-*.txt")):
        reviewer = path.stem.split("-", 1)[1]
        answer = load_json(path.read_text(errors="replace"), "ranking")
        if not answer or not isinstance(answer.get("ranking"), list):
            unusable_b.append(reviewer)
            continue
        rankings[reviewer] = [str(x).strip().upper()[:1] for x in answer["ranking"]]

    if not rankings:
        print("no usable rankings; nothing to aggregate", file=sys.stderr)
        return 1

    letters = sorted({x for order in rankings.values() for x in order})
    mean_rank = {
        letter: statistics.mean([order.index(letter) + 1 for order in rankings.values() if letter in order])
        for letter in letters
    }
    aggregate = sorted(letters, key=lambda x: mean_rank[x])

    print("=== ranking, mean rank across reviewers (lower is better) ===")
    for pos, letter in enumerate(aggregate, 1):
        tag = "  <-- REFERENCE" if letter == reference else ""
        print(f"  {pos}. {letter}  mean {mean_rank[letter]:.2f}   {mapping.get(letter, '?')}{tag}")

    print("\n=== do the reviewers agree with each other? ===")
    correlations = []
    for one, two in combinations(sorted(rankings), 2):
        rho = spearman(rankings[one], rankings[two])
        if rho is not None:
            correlations.append(rho)
            print(f"  {one:8s} vs {two:8s}  rho = {rho:+.2f}")
    median_rho = statistics.median(correlations) if correlations else None

    print("\n=== self-preference: did a reviewer favour its own family? ===")
    clean = [r for r in rankings if r in CONFLICT_FREE]
    for reviewer, family in SAME_FAMILY.items():
        if reviewer not in rankings:
            continue
        letter = next((l for l, src in mapping.items() if family in src), None)
        if letter is None or not clean:
            continue
        mine = rankings[reviewer].index(letter) + 1
        theirs = statistics.mean([rankings[r].index(letter) + 1 for r in clean if letter in rankings[r]])
        gap = theirs - mine
        verdict = "FAVOURED" if gap >= 1 else ("penalised" if gap <= -1 else "no effect")
        print(f"  {reviewer:8s} placed its family's entry ({letter}) at {mine}, "
              f"conflict-free reviewers at {theirs:.2f}  ->  {verdict}")

    print("\n=== pass A findings ===")
    by_impl: dict[str, dict[str, list]] = {}
    unusable_a: list[str] = []
    for path in sorted(args.answers.glob("passA-*.txt")):
        _, letter, reviewer = path.stem.split("-", 2)
        answer = load_json(path.read_text(errors="replace"), "findings")
        if not answer:
            unusable_a.append(path.stem)
            continue
        for finding in answer.get("findings", []):
            by_impl.setdefault(letter, {}).setdefault(reviewer, []).append(finding)

    for letter in sorted(by_impl):
        per = by_impl[letter]
        counts = {r: len(f) for r, f in per.items()}
        real = {r: sum(1 for f in fs if f.get("severity") != "taste") for r, fs in per.items()}
        print(f"  {letter} ({mapping.get(letter, '?')}): findings {counts}, excluding taste {real}")
        # Corroboration is by the file a finding points at, which is the coarsest honest join: two
        # reviewers rarely phrase the same objection alike, and matching on wording would report
        # agreement as disagreement.
        files = {r: {str(f.get("lines", "")).split(":")[0] for f in fs} for r, fs in per.items()}
        if len(files) > 1:
            both = set.intersection(*files.values())
            print(f"      corroborated files: {sorted(both) if both else 'none'}")

    print("\n=== validity, decided by the rules fixed before the answers existed ===")
    print(f"  panel: {len(rankings)} usable ranking(s) from {sorted(rankings)}")
    failures = []
    attention = []

    # A missing reviewer is not one kind of loss. The conflict-free pair IS the reference the
    # conflicted two are measured against, and one ordering cannot tell a biased reviewer from a
    # merely different one - so losing either of them takes the measurement with it. Losing a
    # conflicted reviewer costs one question and leaves the rest standing.
    missing_clean = sorted(CONFLICT_FREE - set(rankings))
    if missing_clean:
        failures.append(f"a conflict-free reviewer is missing from the ranking ({missing_clean}); "
                        f"self-preference has no baseline left to measure against")
    if unusable_b:
        attention.append(f"MISSING from the ranking: {sorted(unusable_b)} - every number above is "
                         f"averaged without them")
    if unusable_a:
        attention.append(f"MISSING from the findings: {sorted(unusable_a)} - corroboration is "
                         f"weaker than it looks wherever one of the two reviewers is absent")

    ref_position = aggregate.index(reference) + 1
    if ref_position == len(aggregate):
        attention.append(f"the reference entry ranked LAST ({ref_position} of {len(aggregate)}) - "
                         f"read it as a finding about that implementation, not about the review")
    if median_rho is not None and median_rho < 0.2:
        failures.append(f"reviewer orderings do not correlate (median rho {median_rho:+.2f})")
    # The question asked is family recognition, not self-recognition, and the distinction is not
    # pedantic: NO reviewer wrote any of these. Opus did not write the sonnet entry, Gemini 3.1 Pro
    # did not write the flash one. An earlier version of this prompt asked "which did you write",
    # whose truthful answer is always "none" - so it would have reported the blinding intact without
    # ever having tested it.
    for path in sorted(args.answers.glob("blind-*.txt")):
        answer = load_json(path.read_text(errors="replace"), "own_family_entry") or {}
        reviewer = path.stem.split("-", 1)[1]
        family = SAME_FAMILY.get(reviewer)
        guess, unreadable = read_blinding_pick(answer.get("own_family_entry"), mapping)
        if unreadable:
            attention.append(f"{reviewer} answered the blinding check with {unreadable!r}, which is "
                             f"neither a letter nor a refusal; read that answer by hand")
        if family and guess and family in mapping[guess]:
            failures.append(
                f"{reviewer} picked out its own family's entry ({guess}) in the blinding check, "
                f"so its ranking of that entry cannot be treated as blind")

    if attention:
        print("  ATTENTION - true, and not a reason to discard anything:")
        for a in attention:
            print(f"    - {a}")

    if failures:
        print("  INVALID:")
        for f in failures:
            print(f"    - {f}")
        print("  The ranking above must not be published as a result.")
        return 2
    print(f"  reference placed {ref_position} of {len(aggregate)}"
          + (f", median reviewer correlation {median_rho:+.2f}" if median_rho is not None else ""))
    print("  no invalidating condition triggered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
