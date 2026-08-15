#!/usr/bin/env bash
# Apply the canonical verification to one run's worktree and print its section-A verdict.
#
# The verification is applied FROM OUTSIDE, after the run, and never exists in the tree the model
# worked in - the reason SWE-bench applies its test_patch from outside. A model that can read the
# acceptance test is being scored on reading comprehension.
#
# It answers section A of the rubric and nothing else. Sections B through F are read off the diff.
#
#   ./score.sh <launch-worktree> [<run-id>] [<run-dir>]
#
# <run-dir> is the run's directory (…/bead-cost/<run-id>), NOT its HOME. Pass it and the scorer
# finds where the run actually left its work, which is not always where it was launched. Omit it
# and the launch worktree is graded as given, which is only correct for a run you know stayed put.
#
# Prints one JSON object on stdout. Everything else goes to stderr, so the caller can collect 45 of
# these into a file without filtering prose out of them.
set -euo pipefail

worktree="${1:?usage: score.sh <run-worktree> [<run-id>] [<run-home>]}"
run_id="${2:-$(basename "$worktree")}"
run_home="${3:-}"
here="$(cd "$(dirname "$0")" && pwd)"

# Asked of git rather than of the filesystem: in a LINKED worktree `.git` is a file pointing at the
# main repo, not a directory, so a `-d` test rejects exactly the worktrees this benchmark runs in.
git -C "$worktree" rev-parse --git-dir >/dev/null 2>&1 ||
    { echo "score: $worktree is not a git worktree" >&2; exit 1; }

# A run is free to move its work, and one did: the global instruction files this sandbox carries
# tell an agent to create its own worktree before its first write, and an agent followed them.
# Given the run's HOME, find where the work actually landed instead of grading the tree the run
# was launched in and abandoned.
if [ -n "$run_home" ]; then
    worktree=$("$here/find-work.sh" "$worktree" "$run_home")
fi
echo "score: grading $worktree" >&2

# The scoring build gets a target dir of its own PER TREE, and the "per tree" half is the whole
# lesson. One directory shared by the scorer was the first design, on the reasoning that scoring
# must never warm or be warmed by a run's build. That reasoning was right and incomplete: every run
# is a clone of the same repository, so every tree presents cargo with the same package name and
# the same version, and one target directory shared across them hands the build artifacts of one
# run's source to another run's test.
#
# It is not a subtle effect. Measured on one unchanged tree at commit cc697df:
#
#   shared scoring target dir  -> a1 true, a2 FALSE, a3 true, a4 FALSE, a5 FALSE   (stable, 4 runs)
#   private, empty target dir  -> a1..a5 all true
#
# The stability is what makes it dangerous. Four identical runs agreeing on a wrong verdict reads
# exactly like a solid measurement, and the wrong verdict is the plausible one - the numeric
# spellings failing is the documented wrong answer for this bead, so it invites being believed.
# Every verdict produced through a shared directory has to be discarded, not re-argued.
#
# The generation is the escape hatch for a poisoned dependency, and it exists because restoring the
# source is NOT enough. Cargo treats a registry source as immutable and fingerprints it by package
# id, so a target directory that compiled `spider` while the crate was patched keeps that rlib and
# never rebuilds it, however pristine the source becomes. Measured: with the source restored and
# verified byte-identical to the published crate, a tree re-scored in an old directory still
# returned the poisoned verdict, and the same tree in a fresh directory returned its real one.
#
# So a generation is abandoned wholesale rather than repaired. Bump BEAD_COST_BUILD_GEN whenever the
# shared registry is found modified; every artifact built under the old number is unreachable from
# then on, and nothing has to be deleted for that to be true.
scoring_root="${BEAD_COST_SCORING_ROOT:-/mnt/build/cargo-target-bead-cost-scoring}"
generation="${BEAD_COST_BUILD_GEN:-2}"
tree_key=$(printf '%s' "$worktree" | md5sum | cut -c1-12)
export CARGO_TARGET_DIR="$scoring_root/gen$generation/$tree_key"

cp "$here/fixtures/benchmark_arch_42q_verify.rs" \
   "$worktree/tests/benchmark_arch_42q_verify.rs"

# The `cd` is checked on its own, and that is not style. Folded into the command substitution as
# `cd … && cargo … || true`, a failure to enter the directory is swallowed by the same `|| true`
# that is there to tolerate a failing test, `output` comes back empty, and the scorer reports "the
# tree did not build" about a directory it never entered. Two different failures, one message.
cd "$worktree" || { echo "score: cannot enter $worktree" >&2; exit 1; }

# `|| true`: an unfixed tree fails this test, which is the expected outcome for most runs and not
# an error in the scorer. The verdict comes from the printed line, never from the exit code - a
# guard on the exit code is precisely the defect that made the first draft of this instrument fail
# every run for a reason unrelated to what it measured.
output=$(cargo test --test benchmark_arch_42q_verify -- --nocapture 2>&1) || true

verdict=$(printf '%s\n' "$output" | grep -m1 '^ARCH42Q_VERDICT ' | cut -d' ' -f2- || true)
targets=$(printf '%s\n' "$output" | grep -m1 '^ARCH42Q_TARGETS ' | cut -d' ' -f2- || true)

rm -f "$worktree/tests/benchmark_arch_42q_verify.rs"

if [ -z "$verdict" ]; then
    # No verdict line means the tree did not build, or the test never reached its print. That is a
    # FAILED RUN, and it is reported as one rather than as five false criteria - a run that cannot
    # compile is not a run that got the behaviour wrong, and blending the two would price a broken
    # harness as a model's mistake.
    printf '{"run":"%s","scored":false,"reason":"no verdict line - the tree did not build or the test did not run"}\n' "$run_id"
    printf '%s\n' "$output" >&2
    exit 0
fi

printf '{"run":"%s","scored":true,"section_a":%s,"targets":%s}\n' "$run_id" "$verdict" "${targets:-null}"
