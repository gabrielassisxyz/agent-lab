#!/usr/bin/env bash
# Narrow the sandbox of one run's worktree so the benchmark's own notes are not reachable from it.
#
# `ai-jail` mounts `~/repositories` read-write by default, and `archeion` carries no `.ai-jail` of
# its own. So a run can read `~/repositories/project-notes/llm-workflow/`, where the rubric lives -
# and the rubric names the hook that produces the plausible-wrong-fix and explains why it is the
# wrong layer. A model that wandered in would be handed the judgement section's answer, and nothing
# about that would show up in the diff.
#
# The fix is `rw_maps`: replacing the default with the run's own worktree means `project-notes` is
# never mounted, rather than merely being impolite to read.
#
# Written into the RUN WORKTREE and never into archeion itself, because archeion's tree is the
# subject of the measurement and must stay at its base commit. It is added to that worktree's
# `.git/info/exclude` so it does not appear as an untracked file in the diff being scored.
#
#   ./harden-worktree.sh <run-worktree>
#
set -euo pipefail

worktree="${1:?usage: harden-worktree.sh <run-worktree>}"
[ -d "$worktree" ] || { echo "harden: $worktree does not exist" >&2; exit 1; }

cat > "$worktree/.ai-jail" <<EOF
# Written by evals/bead_cost/harden-worktree.sh. Not part of archeion.
#
# The default rw_maps is ~/repositories, which puts the benchmark's own rubric inside the jail.
# This run may write to its own worktree and to ~/tmp, and sees nothing else under ~/repositories.
command = ["claude"]
rw_maps = ["$worktree", "~/tmp"]
ro_maps = []
hide_dotdirs = [".password-store"]
mask = []
no_docker = true
allow_tcp_ports = []
EOF

# The worktree's exclude file lives in the main repo's .git, under worktrees/<name>/info/exclude for
# a linked worktree. `git rev-parse --git-path` resolves whichever applies.
exclude="$(git -C "$worktree" rev-parse --git-path info/exclude)"
mkdir -p "$(dirname "$exclude")"
grep -qxF '.ai-jail' "$exclude" 2>/dev/null || echo '.ai-jail' >> "$exclude"

echo "$worktree/.ai-jail"
