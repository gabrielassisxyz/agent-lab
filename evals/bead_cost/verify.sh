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
root="${BEAD_COST_ROOT:-$HOME/tmp/bead-cost}"
run_home_dir="$(dirname "$run_home")"
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

# The credentials each lane actually authenticates with. Checked by name rather than by asking the
# lane, because asking agy costs a request against a weekly window that opens on first use - and
# checked at all because the agy lane's credential is the one that is easy to believe is already
# there: `oauth_creds.json` is copied, looks like a Google credential, and is the wrong file.
agy_token="$HOME/.gemini/antigravity-cli/antigravity-oauth-token"
if [ ! -e "$agy_token" ]; then
    pass "no antigravity token on this machine either - the agy lane is not configured here"
elif [ -s "$run_home/.gemini/antigravity-cli/antigravity-oauth-token" ]; then
    pass "the agy lane's antigravity token came across"
else
    bad "the agy lane's antigravity token is missing - agy will fail auth in seconds and produce no data point"
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

echo "==> the toolchain caches are warm (an empty one is a tax the first run pays and the rest do not)"
# Added after the first full pilot spent part of its hour re-downloading 357 MB of crates and
# 172 MB of npm packages, because the sandbox HOME hid the real caches. That time was then
# indistinguishable from the model's own, and it produced `can't find crate` errors the agent
# worked around instead of the bead.
if [ ! -d "$HOME/.npm" ]; then
    pass ".npm does not exist on this machine either"
elif [ -L "$run_home/.npm" ]; then
    bad ".npm is linked whole - a run's npm bookkeeping races every other run's"
elif [ ! -L "$run_home/.npm/_cacache" ]; then
    bad ".npm/_cacache is not shared - this run will re-download its packages"
else
    pass ".npm is private with _cacache shared"
fi

# The cargo split, asserted in both directions, because getting either half wrong is silent and
# expensive. A shared `src` lets a run edit its dependencies for everyone - which is how an
# untouched base tree started passing the canonical verification, after a run patched `spider` to
# fix the bead inside the crate. A private `cache` re-downloads 357 MB inside the measured hour.
if [ -d "$HOME/.cargo" ]; then
    if [ -L "$run_home/.cargo" ]; then
        bad ".cargo is linked whole - a run can edit the machine's dependency sources for every later run"
    elif [ ! -d "$run_home/.cargo/registry/src" ]; then
        bad ".cargo/registry/src is missing - cargo has nowhere private to extract into"
    elif [ -L "$run_home/.cargo/registry/src" ]; then
        bad ".cargo/registry/src is a link to the shared sources - a run's edits would outlive it"
    else
        pass ".cargo/registry/src is private to this run"
    fi
    for shared in cache index; do
        if [ -L "$run_home/.cargo/registry/$shared" ]; then
            pass ".cargo/registry/$shared is shared (downloads are not re-paid)"
        else
            bad ".cargo/registry/$shared is not shared - this run will re-download the world"
        fi
    done
fi
# Asserted on the artifact rather than on the link: a symlink to an empty directory passes every
# check above and still costs the run a full download.
# -L, because `cache` is now the final component of the path AND a symlink, and find does not
# descend into a terminal symlink without it. Silent when wrong: the count comes back 0 and reads
# as a cold cache rather than as a check looking at the link instead of through it.
crates=$(find -L "$run_home/.cargo/registry/cache" -name "*.crate" 2>/dev/null | wc -l)
if [ "$crates" -gt 100 ]; then
    pass "the crate cache is populated ($crates crates)"
else
    bad "only $crates crates reachable - the cache is linked but not warm"
fi

# The lane's own reachability - added after a pilot run died with `Model "litellm/kimi-k2.7-k1" not
# found` before spending a token, because the sandbox had not copied pi's model catalog - is asked
# further down, inside the jail. Asking it here as well would be asking about a configuration no run
# executes in, which is the mistake the jail section exists to correct.
if command -v pi >/dev/null 2>&1; then
    pass "pi is on PATH"
else
    bad "pi is not on PATH"
fi

if [ -f "$run_home/.pi/agent/mcp.json" ]; then
    if [ "$(tr -d '[:space:]' < "$run_home/.pi/agent/mcp.json")" = "{}" ]; then
        pass "pi's own mcp.json is neutralised"
    else
        bad "pi's mcp.json carries servers - the memory server is reachable for this lane"
    fi
fi

echo "==> there is room to build (a full disk fails a run in a way that blames the model)"
# Added after /mnt/build went from 141 GB free to zero in six hours and took a sweep with it. Every
# run gets a build directory per lane and every scored tree gets one of its own, at roughly 4.5 GB
# each, so a night of runs is tens of gigabytes and the growth is invisible until it is not.
#
# What it costs when unchecked is worse than the space: the runs did not stop, they failed instantly
# and in a loop, each one burning a run id and a strike, so the log filled with lanes resting for
# three consecutive failures that were all one full filesystem. A gate here turns that into a
# refusal to start.
build_root="${BEAD_COST_BUILD_ROOT:-/mnt/build}"
build_free_gb=$(df -BG --output=avail "$build_root" 2>/dev/null | tail -1 | tr -dc '0-9')
if [ -z "$build_free_gb" ]; then
    bad "cannot read free space on $build_root"
elif [ "$build_free_gb" -lt "${BEAD_COST_MIN_FREE_GB:-20}" ]; then
    bad "$build_root has only ${build_free_gb}G free - a run needs room for a lane build and a scoring build"
else
    pass "$build_root has ${build_free_gb}G free"
fi

echo "==> the checkout has a ref namespace of its own (no run can read another run's answer)"
# THE gate this experiment was missing, and the reason the pilot's successors would have been void.
# Runs used to be linked worktrees of the shared subject repository, which share one ref namespace,
# so from inside any of them `git log --all --oneline` opened with:
#
#     6b743bc fix(crawl): decode HTML entities in hrefs before the engine builds URLs
#     08cac62 fix(crawl): decode HTML entities in discovered link hrefs
#
# - an earlier run's commit subject naming both the fix and the layer it belongs in, which is what
# the rubric's judgement section scores. An agent was observed running `git log` looking for `arch-`
# beads mid-run, and none of it would appear in the diff being graded.
#
# Asserted on reachability rather than on the list of ref NAMES. A name-based check passes the
# moment someone adds a branch this script has not been taught about, and the property that matters
# is not what the refs are called - it is that no ref reaches a commit outside the base's history.
checkout="${BEAD_COST_CHECKOUT:-}"
if [ -z "$checkout" ]; then
    bad "set BEAD_COST_CHECKOUT=<run-checkout> - the isolation gates have nothing to check without it"
elif ! git -C "$checkout" rev-parse --git-dir >/dev/null 2>&1; then
    bad "$checkout is not a git repository"
else
    all_commits=$(git -C "$checkout" rev-list --all | wc -l)
    head_commits=$(git -C "$checkout" rev-list HEAD | wc -l)
    if [ "$all_commits" -eq "$head_commits" ]; then
        pass "every ref stays inside the base history ($head_commits commits, no foreign ref)"
    else
        bad "$((all_commits - head_commits)) commit(s) are reachable outside HEAD's history - a sibling run's work is visible here"
        git -C "$checkout" log --all --not HEAD --oneline | head -5 >&2
    fi
    if [ -n "$(git -C "$checkout" tag)" ]; then
        bad "the checkout carries tags - a tag is a ref too, and git log --all walks it"
    else
        pass "no tags"
    fi
    # The bead must still be open. A fixed base means there is nothing left to measure, and every
    # run would be scored against a tree that already passes.
    if git -C "$checkout" log --oneline -20 | grep -qi "arch-42q"; then
        bad "a commit mentioning arch-42q is in the checkout's history - the subject may already be fixed"
    else
        pass "no arch-42q fix in the base history"
    fi
    pass "base commit $(git -C "$checkout" rev-parse --short HEAD)"
fi

echo "==> what the run sees, asked THROUGH THE JAIL rather than from this shell"
# The host can obviously read its own files; the only question that matters is what the run sees,
# and an earlier draft of this script asked the first question and would have passed a sandbox that
# leaked. Every probe below runs the way the run itself is launched - same jail, same HOME - because
# a gate that tests a configuration the run does not use is a gate that reports on nothing. That is
# not hypothetical either: this file used to check the notes through `ai-jail` while the runs were
# launched outside it entirely, so the one contamination vector it named was never actually closed.
notes="$HOME/repositories/project-notes/llm-workflow"
if [ -z "$checkout" ]; then
    bad "BEAD_COST_CHECKOUT is unset, so nothing below can be asked through the jail"
elif [ ! -f "$checkout/.ai-jail" ]; then
    bad "$checkout has no .ai-jail - run harden-worktree.sh, or the default rw_maps mounts all of ~/repositories"
elif ! command -v ai-jail >/dev/null 2>&1; then
    bad "ai-jail is not on PATH, so none of the checks that matter can be made"
else
    # HOME is overridden for the command INSIDE the jail, never for ai-jail itself. ai-jail decides
    # what to bind by enumerating the dotdirs of the HOME it is launched with, so handing it the
    # run's HOME makes it mount that instead of the machine's - and the run then has no ~/.cargo and
    # no mise, which is how the first draft of this check reported "0 crates reachable" and "the
    # model is not known inside the jail" about a sandbox whose only defect was this line. The same
    # two symptoms the pilot burned a run on, produced this time by the checker rather than the
    # sandbox.
    jail() { (cd "$checkout" && ai-jail --exec --no-save-config -- env HOME="$run_home" "$@"); }

    if [ ! -d "$notes" ]; then
        pass "project-notes/llm-workflow is not present on this machine"
    elif jail ls "$notes" >/dev/null 2>&1; then
        bad "a jailed process READ project-notes/llm-workflow - a run can be handed the rubric and the answer key"
    else
        pass "a jailed process cannot read project-notes/llm-workflow"
    fi

    # The sibling runs, on the filesystem rather than through git. Each run directory holds another
    # lane's checkout and its session log; mapping the shared parent would hand a run its siblings
    # by a different road than the one the ref-namespace gate above closes.
    # Single-quoted on purpose: `$0` has to be expanded by the shell INSIDE the jail, against the
    # path passed to it, not by this one before the jail exists.
    # shellcheck disable=SC2016
    siblings=$(jail sh -c 'ls "$0" 2>/dev/null' "$root" | grep -vxF "$(basename "$run_home_dir")" | grep -vxF "_base.git" || true)
    if [ -n "$siblings" ]; then
        bad "a jailed process can list other runs under $root:"
        printf '%s\n' "$siblings" | sed 's/^/        /' >&2
    else
        pass "no other run directory is visible from inside the jail"
    fi

    # /mnt/build is where the subject's own gate builds: bin/ci sets CARGO_TARGET_DIR there when the
    # caller has not. A run that cannot write it fails to build for a reason that is not the bead.
    if jail sh -c 'touch /mnt/build/.bead-cost-verify && rm -f /mnt/build/.bead-cost-verify' 2>/dev/null; then
        pass "/mnt/build is writable inside the jail (bin/ci builds there)"
    else
        bad "/mnt/build is not writable inside the jail - bin/ci will fail for a reason that is not the bead"
    fi

    # Asserted on the crate count rather than on the mount, for the reason the host-side check is:
    # a linked but cold cache passes every structural test and still costs the run a full download.
    # Single-quoted for the same reason: `$HOME` is the run's HOME as the jail sees it.
    # shellcheck disable=SC2016
    jailed_crates=$(jail sh -c 'find -L "$HOME/.cargo/registry/cache" -name "*.crate" 2>/dev/null | wc -l' || echo 0)
    if [ "${jailed_crates:-0}" -gt 100 ]; then
        pass "the crate cache is reachable inside the jail ($jailed_crates crates)"
    else
        bad "only ${jailed_crates:-0} crates reachable inside the jail - the run will re-download the world"
    fi

    # `bin/worktree new` is the first thing the global instruction files tell an agent to do, and it
    # opens with `git fetch origin`. Without a reachable origin it aborts, and the run then works in
    # a way no ordinary session would.
    if jail git ls-remote origin >/dev/null 2>&1; then
        pass "origin is reachable inside the jail (bin/worktree new can fetch)"
    else
        bad "origin is unreachable inside the jail - bin/worktree new will abort before the run starts"
    fi

    # Asked of the lane that will actually run it. The first draft asked pi's catalog whatever the
    # lane was, so the agy lane failed this gate for a model pi was never going to be given - a gate
    # reporting on a question nobody asked, which is the same class of mistake as checking the jail
    # while launching outside it.
    #
    # For agy this is also the cheapest possible auth check: `agy models` needs a working login and
    # no completion, so a lane whose credentials did not come across fails here instead of failing
    # in seconds once the run has started and the operator has walked away.
    if [ -n "${BEAD_COST_MODEL:-}" ]; then
        case "${BEAD_COST_LANE:-pi}" in
            agy) lane_models=$(jail agy models 2>/dev/null || true) ;;
            *)   lane_models=$(jail pi --list-models 2>/dev/null || true) ;;
        esac
        if printf '%s\n' "$lane_models" | grep -qF "${BEAD_COST_MODEL#litellm/}"; then
            pass "$BEAD_COST_MODEL is known to the ${BEAD_COST_LANE:-pi} lane inside the jail"
        else
            bad "$BEAD_COST_MODEL is NOT known to the ${BEAD_COST_LANE:-pi} lane inside the jail - catalog or credentials did not come across"
        fi
    fi
fi

echo
if [ "$fail" -eq 0 ]; then
    echo "==> sandbox verified"
else
    echo "==> sandbox NOT verified - do not run until every line above is ok" >&2
fi
exit "$fail"
