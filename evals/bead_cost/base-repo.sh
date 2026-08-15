#!/usr/bin/env bash
# Build the isolated base repository every run is cut from, holding ONE branch at ONE commit.
#
# WHY this exists, and it is the most expensive lesson the pilot left. Runs used to be worktrees of
# the real subject repository, which means they share one object store and one ref namespace. From
# inside any of them `git log --all --oneline` printed, as its top two lines:
#
#     6b743bc fix(crawl): decode HTML entities in hrefs before the engine builds URLs
#     08cac62 fix(crawl): decode HTML entities in discovered link hrefs
#
# The commit subject of an earlier run names the fix AND the layer it belongs in, which is exactly
# what the rubric's judgement section scores. One agent was observed running `git log` looking for
# `arch-` beads during its run, so this is a path agents take rather than one they could take. And
# none of it shows up in the diff being graded: a run handed the answer produces the same artefact
# as a run that derived it.
#
# A branch is only visible if a ref points at it, so the fix is a ref namespace per run. This builds
# the shared half: a bare repository fetched from the subject at exactly one commit, carrying no
# other branch, no tag and no remote to fetch the rest back from. `checkout.sh` clones a run from
# it. Objects outside that commit's history are never copied here, so they cannot be reached even
# by hash.
#
#   ./base-repo.sh [<base-commit>]      # prints "<bare-repo-path> <base-commit>"
#
set -euo pipefail

root="${BEAD_COST_ROOT:-$HOME/tmp/bead-cost}"
subject="${BEAD_COST_SUBJECT:-$HOME/repositories/archeion}"
base_repo="$root/_base.git"
branch="${BEAD_COST_BASE_BRANCH:-main}"

[ -d "$subject/.git" ] || { echo "base-repo: no repository at $subject" >&2; exit 1; }

want="${1:-}"
[ -n "$want" ] || want=$(git -C "$subject" rev-parse "$branch")
want=$(git -C "$subject" rev-parse "$want^{commit}")

# An existing base is checked rather than rebuilt. Rebuilding silently is how a set of runs ends up
# split across two different base commits, which voids the comparison and leaves no trace.
if [ -d "$base_repo" ]; then
    have=$(git -C "$base_repo" rev-parse "refs/heads/$branch" 2>/dev/null || echo none)
    if [ "$have" != "$want" ]; then
        echo "base-repo: $base_repo is at $have, not the requested $want." >&2
        echo "           Runs already cut from it are measured on a different tree. Move it aside" >&2
        echo "           deliberately if the base really is changing." >&2
        exit 1
    fi
else
    mkdir -p "$root"
    git init --quiet --bare --initial-branch="$branch" "$base_repo"
    # Fetched by ref rather than by hash: a plain `git fetch <path> <sha>` needs the server side to
    # allow reachable-SHA1-in-want, which is off by default and fails with a message about the
    # object not being advertised. The tip comes across, then the ref is moved back to the wanted
    # commit if it is an ancestor.
    git -C "$base_repo" fetch --quiet --no-tags "$subject" "$branch:refs/heads/$branch"
    if [ "$(git -C "$base_repo" rev-parse "refs/heads/$branch")" != "$want" ]; then
        git -C "$base_repo" merge-base --is-ancestor "$want" "refs/heads/$branch" 2>/dev/null || {
            echo "base-repo: $want is not an ancestor of $subject's $branch" >&2
            exit 1
        }
        git -C "$base_repo" update-ref "refs/heads/$branch" "$want"
        # Objects for the commits that were just dropped are still in the pack. They are unreachable
        # by ref, so `git log --all` cannot find them, but gc is what actually removes them.
        git -C "$base_repo" reflog expire --expire=now --all 2>/dev/null || true
        git -C "$base_repo" gc --quiet --prune=now
    fi
    git -C "$base_repo" symbolic-ref HEAD "refs/heads/$branch"
fi

# Asserted on the artifact, not on the commands above having exited zero: what matters is the set of
# refs a clone of this will inherit, and that is a thing to look at.
refs=$(git -C "$base_repo" for-each-ref --format='%(refname)')
if [ "$refs" != "refs/heads/$branch" ]; then
    echo "base-repo: $base_repo carries refs beyond $branch, so a run cut from it would see them:" >&2
    printf '%s\n' "$refs" | sed 's/^/  /' >&2
    exit 1
fi
if [ -n "$(git -C "$base_repo" remote)" ]; then
    echo "base-repo: $base_repo has a remote - a run could fetch the sibling branches back" >&2
    exit 1
fi

echo "$base_repo $want"
