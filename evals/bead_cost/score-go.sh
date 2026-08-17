#!/usr/bin/env bash
# Grade one run of a Go subject against its bead's canonical verification.
#
# The shape follows `score.sh` and the reasoning behind each choice is there; what differs is the
# subject, and two things fall out of it.
#
# The verdict is GRADED, not binary. `go test -json` reports one result per test function, and the
# vendored file carries sixteen of them, so a run that gets reservation right and release-once wrong
# scores differently from one that got neither. A binary verdict on a bead this size would sit at
# the floor for every partial attempt and measure nothing - which is the failure mode the first
# subject's saturated metrics already demonstrated.
#
# The vendored file OVERWRITES whatever is in the tree, and here that is load-bearing rather than
# precautionary. Unlike the first subject, this bead's test already exists in the base tree - it is
# how the bead states its contract, and the run can read it, edit it, or delete it. Grading the
# tree's own copy would let a run pass by weakening the test, which is not a thing to detect after
# the fact but a thing to make impossible.
#
# THE WHOLE TEST SURFACE is restored, not just the vendored file, and one run proved why. The
# canonical test calls helpers it does not define - `reserveAndFinalize` lives in `rate_test.go`,
# `reserveFinalizeRelease` in `blackout_test.go` - so a run that merely MOVES a helper leaves the
# vendored file unable to compile and scores zero with `build_failed`, indistinguishable from a run
# whose implementation is broken. Restoring every test file in the graded package from the base
# makes the verdict a function of the production code and nothing else, which is what it always
# claimed to be.
#
# And it is done on a COPY. The run's tree is evidence: its implementation has to survive being
# graded, and being graded twice, because re-scoring from artefacts already on disk is how a metric
# gets repaired without paying for the runs again. The previous arrangement wrote the fixture into
# the run's own tree and left it there, which also made the collector's `dirty` flag report the
# scorer's residue rather than the agent's work.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
worktree="${1:?usage: score-go.sh <worktree> <run-id> [<run-home>]}"
run_id="${2:?usage: score-go.sh <worktree> <run-id> [<run-home>]}"
run_home="${3:-}"

fixture="${BEAD_COST_GO_FIXTURE:-$here/fixtures/llmux_5vg_reservation_test.go}"
target="${BEAD_COST_GO_FIXTURE_PATH:-internal/route/reservation_test.go}"
package="${BEAD_COST_GO_PACKAGE:-./internal/route/}"

git -C "$worktree" rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
    { echo "score: $worktree is not a git worktree" >&2; exit 1; }

# A run is free to move its work, and one did: the instruction files this sandbox carries tell an
# agent to create its own worktree before its first write, and an agent followed them.
if [ -n "$run_home" ]; then
    worktree=$("$here/find-work.sh" "$worktree" "$run_home")
fi
echo "score: grading $worktree" >&2

# The tree the run left is never written to. `origin/main` is the base in every clone, including
# the ones that committed on top of it, so the pristine test surface is recoverable from the run's
# own repository without needing to be told which commit that was.
base_ref="${BEAD_COST_BASE_REF:-origin/main}"
package_dir="${package#./}"
package_dir="${package_dir%/}"

source_tree="$worktree"

# The criteria come from the FIXTURE, not from what reported. A tree that does not build reports
# nothing, and grading only what reported would score it as a perfect zero-criterion run. Read from
# the vendored file so the list cannot drift from the verification actually applied.
mapfile -t expected < <(grep -oE '^func (Test[A-Za-z0-9_]+)' "$fixture" | cut -d' ' -f2)
[ "${#expected[@]}" -gt 0 ] ||
    { echo "score: no Test functions found in $fixture" >&2; exit 1; }

# The build cache is the scorer's own and per tree, for the reason `score.sh` spells out at length:
# every run is a clone of one repository, so a shared cache hands one tree's compiled artefacts to
# another tree's test. Go keys its cache on content rather than on package identity, which makes
# that collision far less likely than cargo's - and "far less likely" is not a property to build a
# measurement on.
# Keyed on the RUN's tree, not on the disposable copy: the copy has a fresh path every time, and
# keying on it would hand every re-score a cold cache and call it isolation.
tree_key=$(printf '%s' "$source_tree" | md5sum | cut -c1-12)
export GOCACHE="${BEAD_COST_GO_SCORING_ROOT:-/mnt/build/go-build-bead-cost-scoring}/$tree_key"
mkdir -p "$GOCACHE"

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

# TWO REGIMES, because one number was answering two questions and only reporting one of them.
#
#   contract      the canonical file over the tree as the run left it. Whether the sixteen
#                 behaviours are implemented, and nothing else.
#   legacy        the same, plus every test file in the package restored from the base commit.
#                 Whether they are implemented AND the pre-existing public API survived.
#
# The restore is what made the second necessary and the first invisible. The canonical file calls
# helpers it does not define - `reserveAndFinalize` lives in `rate_test.go` - and the base version of
# that helper calls methods a refactor may have removed. So a run that reorganised the package's API
# and migrated its tests to match fails to COMPILE under the restore, and scores zero with
# `build_failed` before one canonical assertion runs. Measured on this campaign: eight runs across
# three arms passed all sixteen on their own tree while being recorded as having solved nothing.
#
# The restore still earns its place, and that is why it stays: it is what stops a run passing by
# weakening the very test that states the contract. Both facts are true, so both are reported.
grade() {  # <graded-dir> <output-json>
    local graded="$1" out="$2" report
    ( cd "$graded" || exit 1
      # `|| true`: a tree that has not implemented the bead fails these tests, which is the expected
      # outcome for most runs and not an error in the scorer. The verdict is read from the report,
      # never from the exit code.
      report=$(go test -json -count=1 "$package" 2>&1) || true
      printf '%s\n' "$report" | "$here/go_verdict.py" "$run_id" "${expected[@]}" > "$out" )
}

# Regime 1: the run's own tree, with only the contract replaced.
contract_tree="$workdir/contract"
mkdir -p "$contract_tree"
cp -a "$source_tree/." "$contract_tree/"
cp "$fixture" "$contract_tree/$target"
grade "$contract_tree" "$workdir/contract.json"

# Regime 2: the same, with the package's whole test surface back at the base commit.
legacy_tree="$workdir/legacy"
mkdir -p "$legacy_tree"
cp -a "$source_tree/." "$legacy_tree/"
while IFS= read -r test_file; do
    [ -n "$test_file" ] || continue
    git -C "$source_tree" show "$base_ref:$test_file" > "$legacy_tree/$test_file"
done < <(git -C "$source_tree" ls-tree --name-only "$base_ref" "$package_dir/" | grep '_test\.go$' || true)
cp "$fixture" "$legacy_tree/$target"
grade "$legacy_tree" "$workdir/legacy.json"

"$here/go_verdict.py" --merge "$run_id" "$workdir/contract.json" "$workdir/legacy.json"
