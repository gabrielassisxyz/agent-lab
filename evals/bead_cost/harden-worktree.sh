#!/usr/bin/env bash
# Narrow the sandbox of one run's checkout so nothing outside that run is reachable from it.
#
# `ai-jail` mounts `~/repositories` read-write by default, and the subject repository carries no
# `.ai-jail` of its own. So a run can read `~/repositories/project-notes/llm-workflow/`, which holds
# the rubric - it names the hook that produces the plausible-wrong-fix and explains why it is the
# wrong layer - and the canonical verification, which is the answer key itself. A model that
# wandered in would be handed the judgement section's answer, and nothing about that would show up
# in the diff.
#
# The fix is `rw_maps`: replacing the default with the run's own directory means `project-notes` is
# never mounted, rather than merely being impolite to read.
#
# The run directory rather than all of `~/tmp`, which is what this wrote first. Every run's
# directory lives under `~/tmp/bead-cost/`, so mapping the parent hands each run its siblings -
# their checkouts, their session logs, their solutions. That is the same leak the per-run clone
# closes on the git side, arriving by the filesystem instead.
#
# `/mnt/build` is read-write because the subject's own gate puts its build there: `bin/ci` sets
# CARGO_TARGET_DIR under /mnt/build when the caller has not. Without it the run's build fails for a
# reason that has nothing to do with the bead.
#
# The base repository is read-only rather than absent, because `bin/worktree new` - which the global
# instruction files tell an agent to run before its first write - starts with `git fetch origin`.
# Read-only is what lets the fetch work while making it impossible for one run to push anything
# other runs would then clone.
#
# Written into the RUN CHECKOUT and never into the subject repository, whose tree is the measurement
# and must stay at its base commit. It is added to the checkout's `.git/info/exclude` so it does not
# appear as an untracked file in the diff being scored.
#
#   ./harden-worktree.sh <run-checkout> [<run-dir>] [<base-repo>]
#
set -euo pipefail

checkout="${1:?usage: harden-worktree.sh <run-checkout> [<run-dir>] [<base-repo>]}"
[ -d "$checkout" ] || { echo "harden: $checkout does not exist" >&2; exit 1; }

root="${BEAD_COST_ROOT:-$HOME/tmp/bead-cost}"
run_dir="${2:-$checkout}"
base_repo="${3:-$root/_base-$(basename "${BEAD_COST_SUBJECT:-$HOME/repositories/archeion}").git}"

ro_maps=()
[ -d "$base_repo" ] && ro_maps+=("\"$base_repo\"")
# Go's module cache, when the machine has one. It has to be named here because ai-jail binds the
# DOTDIRS of the launching HOME, and `~/go` is not one - so the sandbox's symlink to it dangles, and
# the failure reads `go: could not create module cache: … file exists`, which sounds like a
# permissions or leftover-directory problem and is neither. Read-only: at 9.8 GB it cannot be copied
# per run, and the alternative to mounting it is every run re-downloading its dependencies through a
# jail that deliberately has no route to the internet.
[ -d "$HOME/go/pkg/mod" ] && ro_maps+=("\"$HOME/go/pkg/mod\"")
ro_line=$(IFS=, ; echo "${ro_maps[*]}")

cat > "$checkout/.ai-jail" <<EOF
# Written by evals/bead_cost/harden-worktree.sh. Not part of the subject repository.
#
# The default rw_maps is ~/repositories, which puts the benchmark's own rubric and its canonical
# verification inside the jail. This run may write inside its own run directory and to the shared
# build area; it sees no other run, and nothing else under ~/repositories.
command = ["claude"]
rw_maps = ["$run_dir", "/mnt/build"]
ro_maps = [$ro_line]
hide_dotdirs = [".password-store"]
mask = []
no_docker = true
allow_tcp_ports = []
EOF

# The exclude file lives in .git/info/exclude for a clone and under worktrees/<name>/info/exclude for
# a linked worktree. `git rev-parse --git-path` resolves whichever applies.
#
# --path-format=absolute is load-bearing. Without it the answer is relative to the repository root,
# so for a clone it comes back as the bare `.git/info/exclude` and the `mkdir -p` below then runs
# against whatever directory the caller happened to be standing in. That failed loudly here only
# because the caller was itself a linked worktree, where `.git` is a file - from anywhere else it
# would have quietly created a stray `.git/info/` and written the exclude into the wrong repository.
exclude="$(git -C "$checkout" rev-parse --path-format=absolute --git-path info/exclude)"
mkdir -p "$(dirname "$exclude")"
grep -qxF '.ai-jail' "$exclude" 2>/dev/null || echo '.ai-jail' >> "$exclude"

echo "$checkout/.ai-jail"
