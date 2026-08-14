#!/usr/bin/env bash
# Prove the bead-cost sandbox before run 1, rather than assume it.
#
# This exists because `ai-jail` is a filesystem blast-radius control and NOT a state boundary: it
# hard-requires ~/.claude and ~/.config read-write and refuses to hide them, so inside the jail
# every run shares one memory store and one session history. Believing otherwise is the trap, and
# a trap nobody checks is a trap that survives into the results.
#
# Every check below asserts an ARTIFACT - a file that is present, a file that is absent, a path
# that cannot be read - never that a command exited zero.
#
#   ./verify.sh <run-home>
#
set -euo pipefail

run_home="${1:?usage: verify.sh <run-home>}"
fail=0

pass() { printf '  ok    %s\n' "$1"; }
bad()  { printf '  FAIL  %s\n' "$1"; fail=1; }

echo "==> the constants arrived (a stripped environment measures a machine nobody owns)"
for f in .claude/CLAUDE.md .codex/AGENTS.md .gemini/GEMINI.md .pi/agent/AGENTS.md; do
    if [ -s "$run_home/$f" ]; then pass "$f is present and non-empty"; else bad "$f is missing or empty"; fi
done

# The routing rule is the newest block in the generated configs, so its absence means the sandbox
# copied a stale file rather than the one a real session reads.
if grep -q "Cheap-lane routing" "$run_home/.claude/CLAUDE.md" 2>/dev/null; then
    pass "the global config carries the current rule set"
else
    bad "the global config predates the cheap-lane routing rule - it is a stale copy"
fi

skills=$(find "$run_home/.claude/skills" -maxdepth 1 -mindepth 1 2>/dev/null | wc -l)
if [ "$skills" -gt 0 ]; then pass "the skill library is present ($skills entries)"; else bad "no skills - the context floor is not the real one"; fi

echo "==> the state is empty (run N must not start where run N-1 finished)"
for d in .claude/projects .codex/sessions .pi/agent/sessions .local/share/ai-memory; do
    if [ ! -d "$run_home/$d" ]; then
        bad "$d does not exist - the tool will fall back to the real HOME"
    elif [ -z "$(find "$run_home/$d" -mindepth 1 -print -quit 2>/dev/null)" ]; then
        pass "$d is empty"
    else
        bad "$d already holds data - this run can read a previous run's work"
    fi
done

echo "==> no MCP server is configured (ai-memory writes back; the web-reaching ones let a model look the answer up)"
if [ -f "$run_home/.claude.json" ]; then
    if python3 -c "
import json,sys
config = json.load(open(sys.argv[1]))
servers = list(config.get('mcpServers') or {})
for project in (config.get('projects') or {}).values():
    if isinstance(project, dict):
        servers += list(project.get('mcpServers') or {})
sys.exit(1 if servers else 0)
" "$run_home/.claude.json"; then
        pass "no mcpServers in .claude.json"
    else
        bad "mcpServers survived into the sandbox"
    fi
else
    pass "no .claude.json to carry servers"
fi

echo "==> the benchmark's own notes are out of reach (the rubric names the plausible-wrong-fix)"
# Checked THROUGH THE JAIL, not on the host. The host can obviously read its own files; the only
# question that matters is what a run sees, and the first draft of this script asked the wrong one
# and would have passed a sandbox that leaked.
notes="$HOME/repositories/project-notes/llm-workflow"
if [ ! -d "$notes" ]; then
    pass "project-notes/llm-workflow is not present on this machine"
elif [ -z "${BEAD_COST_WORKTREE:-}" ]; then
    bad "set BEAD_COST_WORKTREE=<run-worktree> so this can be checked inside the jail, not on the host"
elif [ ! -f "$BEAD_COST_WORKTREE/.ai-jail" ]; then
    bad "$BEAD_COST_WORKTREE has no .ai-jail - run harden-worktree.sh, or the default rw_maps mounts all of ~/repositories"
elif ! command -v ai-jail >/dev/null 2>&1; then
    bad "ai-jail is not on PATH, so the one check that matters cannot be made"
elif (cd "$BEAD_COST_WORKTREE" && ai-jail --exec ls "$notes" >/dev/null 2>&1); then
    bad "a jailed process READ project-notes/llm-workflow - a run can be handed section B's answer"
else
    pass "a jailed process cannot read project-notes/llm-workflow"
fi

echo "==> the subject repo is at one base commit, and no run branch is visible to another"
archeion="${BEAD_COST_SUBJECT:-$HOME/repositories/archeion}"
if [ -d "$archeion/.git" ]; then
    dirty=$(git -C "$archeion" status --porcelain | wc -l)
    if [ "$dirty" -eq 0 ]; then pass "archeion is clean"; else bad "archeion has $dirty uncommitted change(s) - runs would branch off an unrecorded tree"; fi
    if git -C "$archeion" log --oneline -1 --format=%H >/dev/null 2>&1; then
        pass "base commit $(git -C "$archeion" rev-parse --short HEAD)"
    fi
    # The bead must still be open. A merged fix means there is nothing left to measure, and every
    # later run would be scored against a tree that already passes.
    if git -C "$archeion" log --oneline -20 | grep -qi "arch-42q"; then
        bad "a commit mentioning arch-42q is in history - the subject may already be fixed"
    else
        pass "no arch-42q fix in recent history"
    fi
else
    bad "archeion not found at $archeion"
fi

echo
if [ "$fail" -eq 0 ]; then
    echo "==> sandbox verified"
else
    echo "==> sandbox NOT verified - do not run until every line above is ok" >&2
fi
exit "$fail"
