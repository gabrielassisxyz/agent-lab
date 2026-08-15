#!/usr/bin/env bash
# Cut one run's checkout from the isolated base, so it has a ref namespace of its own.
#
# This replaces `git worktree add` on the shared subject repository. A linked worktree shares the
# object store AND the ref namespace of the repository it came from, which means every run could
# list every other run's branch and read its commit subjects - and those subjects name the fix. See
# `base-repo.sh` for the evidence and the reasoning; this is the per-run half of it.
#
# A clone rather than a copy of the worktree, because the isolation has to be a property of the
# repository rather than of anyone's discipline: with only `main` in the base, there is no ref for
# `git log --all` to walk, whatever the agent decides to try.
#
#   ./checkout.sh <run-id> [<base-commit>]     # prints the checkout path
#
set -euo pipefail

run_id="${1:?usage: checkout.sh <run-id> [<base-commit>]}"
here="$(cd "$(dirname "$0")" && pwd)"
root="${BEAD_COST_ROOT:-$HOME/tmp/bead-cost}"
subject="${BEAD_COST_SUBJECT:-$HOME/repositories/archeion}"
branch="${BEAD_COST_BASE_BRANCH:-main}"

run_dir="$root/$run_id"
checkout="$run_dir/$(basename "$subject")"

if [ -e "$checkout" ]; then
    echo "checkout: $checkout already exists - a run id is used once, so two runs are never mixed" >&2
    exit 1
fi

read -r base_repo base_commit < <("$here/base-repo.sh" "${2:-}")

mkdir -p "$run_dir"
# --no-hardlinks: hardlinked object files would put every base object one inode away from the shared
# base repository. The base carries only this commit's history so there is nothing there to leak,
# but a run's repository being physically separate is what keeps that true if the base ever changes.
git clone --quiet --no-hardlinks "$base_repo" "$checkout"
git -C "$checkout" checkout --quiet "$base_commit"
git -C "$checkout" checkout --quiet -B "$branch" "$base_commit"

# The issue tracker is a constant, not state: a real session in this repository has it, every lane
# gets the identical copy, and it therefore cancels in a comparison of lanes. COPIED rather than
# symlinked for the reason every other constant is - a link lets a run close the bead in the shared
# database and change what the next run reads.
if [ -d "$subject/.beads" ]; then
    cp -r "$subject/.beads" "$checkout/.beads"
fi

"$here/harden-worktree.sh" "$checkout" "$run_dir" "$base_repo" >/dev/null

echo "$checkout"
