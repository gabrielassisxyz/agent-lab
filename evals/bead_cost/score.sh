#!/usr/bin/env bash
# Apply the canonical verification to one run's worktree and print its section-A verdict.
#
# The verification is applied FROM OUTSIDE, after the run, and never exists in the tree the model
# worked in - the reason SWE-bench applies its test_patch from outside. A model that can read the
# acceptance test is being scored on reading comprehension.
#
# It answers section A of the rubric and nothing else. Sections B through F are read off the diff.
#
#   ./score.sh <run-worktree> [<run-id>]
#
# Prints one JSON object on stdout. Everything else goes to stderr, so the caller can collect 45 of
# these into a file without filtering prose out of them.
set -euo pipefail

worktree="${1:?usage: score.sh <run-worktree> [<run-id>]}"
run_id="${2:-$(basename "$worktree")}"
here="$(cd "$(dirname "$0")" && pwd)"

# Asked of git rather than of the filesystem: in a LINKED worktree `.git` is a file pointing at the
# main repo, not a directory, so a `-d` test rejects exactly the worktrees this benchmark runs in.
git -C "$worktree" rev-parse --git-dir >/dev/null 2>&1 ||
    { echo "score: $worktree is not a git worktree" >&2; exit 1; }

# The scoring build gets its own target dir, so it never warms - or is warmed by - a run's build.
# Wall clock is measured on the run, never here, but a shared cache would still let one run's
# compile pay for another's.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/mnt/build/cargo-target-bead-cost-scoring}"

cp "$here/fixtures/benchmark_arch_42q_verify.rs" \
   "$worktree/tests/benchmark_arch_42q_verify.rs"

# `|| true`: an unfixed tree fails this test, which is the expected outcome for most runs and not
# an error in the scorer. The verdict comes from the printed line, never from the exit code - a
# guard on the exit code is precisely the defect that made the first draft of this instrument fail
# every run for a reason unrelated to what it measured.
output=$(cd "$worktree" && cargo test --test benchmark_arch_42q_verify -- --nocapture 2>&1 || true)

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
