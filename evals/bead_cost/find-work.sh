#!/usr/bin/env bash
# Find the tree a run actually left its work in, rather than assuming it is the one it was launched
# in. Prints one path on stdout.
#
# This exists because a run does not have to stay where it was put, and the first pilot did not.
# The sandbox carries the machine's real global instruction files - deliberately, because they are
# the context floor a lane actually pays - and those files open with a gate saying that before the
# first write you create your own worktree. The agent read it, noticed it had been dropped into a
# worktree whose branch had nothing to do with the bead, and did the correct thing: it made its
# own. Scoring the launch worktree would have graded a tree the run abandoned after a few minutes,
# and reported a good lane as a bad one.
#
# The fix is not to forbid it. Forbidding means stripping the very rule that makes the environment
# real, to protect an assumption the scorer never had to make. Discovery is cheap; dictation costs
# the realism the whole experiment is built on.
#
#   ./find-work.sh <launch-worktree> <run-home> [<base-commit>]
set -euo pipefail

launch="${1:?usage: find-work.sh <launch-worktree> <run-home> [<base-commit>]}"
run_home="${2:?usage: find-work.sh <launch-worktree> <run-home> [<base-commit>]}"
base="${3:-}"

repo_root=$(git -C "$launch" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || {
    echo "find-work: $launch is not a git worktree" >&2
    exit 1
}
main_tree=$(dirname "$repo_root")
[ -n "$base" ] || base=$(git -C "$main_tree" rev-parse HEAD)

# Candidates: the tree the run was launched in, plus every worktree of the same repository that
# lives under this run's HOME. Scoped to the run's HOME on purpose - another session's worktree
# elsewhere on the machine is not this run's work, and picking one up would be worse than missing it.
candidates=$(
    {
        echo "$launch"
        git -C "$main_tree" worktree list --porcelain 2>/dev/null |
            awk '/^worktree /{print $2}' |
            grep -F "$run_home" || true
    } | awk '!seen[$0]++'
)

best=""
best_changes=0
for tree in $candidates; do
    [ -d "$tree" ] || continue
    # Committed work and uncommitted work both count: a run that finished the change and never
    # committed is not a run that did nothing, and grading it as one is the mistake this whole
    # script exists to prevent.
    committed=$(git -C "$tree" diff --numstat "$base" HEAD 2>/dev/null | wc -l)
    dirty=$(git -C "$tree" diff --numstat 2>/dev/null | wc -l)
    changes=$((committed + dirty))
    if [ "$changes" -gt "$best_changes" ]; then
        best="$tree"
        best_changes="$changes"
    fi
done

if [ -z "$best" ]; then
    # Falling back to the launch tree rather than failing: an empty result is a real outcome for a
    # run that produced nothing, and the caller scores it as such.
    echo "find-work: no candidate carries changes; falling back to the launch tree" >&2
    echo "$launch"
    exit 0
fi

[ "$best" = "$launch" ] || echo "find-work: the run moved its work to $best" >&2
echo "$best"
