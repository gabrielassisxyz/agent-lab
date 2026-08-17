#!/usr/bin/env bash
# Build the isolated HOME one bead-cost run executes in.
#
# The rule this implements: keep everything CONSTANT across runs, isolate everything that VARIES.
# A constant shifts every lane by the same amount and cancels in a comparison of lanes - the global
# config files are not overhead to be stripped, they are the floor the decision is about. What
# ruins the measurement is state that differs between runs, and worst of all state that accumulates
# as the runs go, so the last lane is measured on an easier problem than the first.
#
# Why an overridden HOME and not a per-tool flag: measured, and documented for agy specifically -
# GEMINI_CLI_HOME relocates the conversation store but NOT the context file. Only HOME moves both.
# Note that the documented agy recipe deliberately STRIPS the context file; here the opposite is
# wanted, so the constants are copied in and only the state is left empty.
#
#   ./sandbox.sh <run-id>        # prints the HOME it built
#
set -euo pipefail

run_id="${1:?usage: sandbox.sh <run-id>}"
root="${BEAD_COST_ROOT:-$HOME/tmp/bead-cost}"
run_home="$root/$run_id/home"

if [ -e "$run_home" ]; then
    echo "sandbox: $run_home already exists - a run id is used once, so its data is never" >&2
    echo "         two runs mixed. Remove it deliberately or pick another id." >&2
    exit 1
fi

mkdir -p "$run_home"

# ---------------------------------------------------------------------------
# The constants: copied, never symlinked.
#
# A symlink would let a run write back into the real config and change what every later run reads -
# which is the accumulating-state failure this whole script exists to prevent.
# ---------------------------------------------------------------------------
copy_constant() {
    local src="$1" dest="$run_home/$2"
    [ -e "$src" ] || return 0
    mkdir -p "$(dirname "$dest")"
    cp -r "$src" "$dest"
}

copy_constant "$HOME/.claude/CLAUDE.md"            ".claude/CLAUDE.md"
copy_constant "$HOME/.claude/settings.json"        ".claude/settings.json"
copy_constant "$HOME/.claude/skills"               ".claude/skills"
copy_constant "$HOME/.codex/AGENTS.md"             ".codex/AGENTS.md"
copy_constant "$HOME/.codex/skills"                ".codex/skills"
# codex resolves its home from HOME, so a run with an overridden HOME reads THIS config and no
# other - measured, including that nothing lands back in the real `~/.codex/sessions`. The file is
# copied for the same reason every other harness's config is: it is a constant, identical for every
# lane, so it cancels in a comparison of lanes, and a lane stripped of it measures a machine nobody
# owns. Its MCP servers are neutralised at the call site rather than here, so this stays a copy.
#
# `hooks.json` is deliberately NOT copied. Those hooks fire on session start, and in a
# non-interactive run they have been observed taking the turn over to announce chores instead of
# doing the work asked for - which would be recorded as the model wandering off.
copy_constant "$HOME/.codex/config.toml"           ".codex/config.toml"
# The model catalogue codex keeps on disk. It is copied so the pre-flight gate can reject a model id
# this harness does not serve WITHOUT spending a request - the gate that accepts an unknown id is
# worse than no gate, because it builds the environment, warms the build and fails inside the
# measured window.
copy_constant "$HOME/.codex/models_cache.json"     ".codex/models_cache.json"
copy_constant "$HOME/.gemini/GEMINI.md"            ".gemini/GEMINI.md"
copy_constant "$HOME/.pi/agent/AGENTS.md"          ".pi/agent/AGENTS.md"
# pi keeps its provider catalog, its auth and its extensions beside that file, and all three are
# CONSTANTS rather than state: without models.json the litellm ids are simply not known, and the
# pilot run that found this failed with `Model "litellm/kimi-k2.7-k1" not found` before spending a
# single token. The npm cache is copied for the same reason it is not state - without it pi
# re-bootstraps itself on every run, which is noise in the wall clock and nothing else.
copy_constant "$HOME/.pi/agent/models.json"        ".pi/agent/models.json"
copy_constant "$HOME/.pi/agent/models-store.json"  ".pi/agent/models-store.json"
copy_constant "$HOME/.pi/agent/settings.json"      ".pi/agent/settings.json"
copy_constant "$HOME/.pi/agent/auth.json"          ".pi/agent/auth.json"
copy_constant "$HOME/.pi/agent/extensions"         ".pi/agent/extensions"
copy_constant "$HOME/.pi/agent/npm"                ".pi/agent/npm"
copy_constant "$HOME/.config/opencode/AGENTS.md"   ".config/opencode/AGENTS.md"

# Credentials are constants too: without them there is no run at all. They are copied rather than
# linked for the same write-back reason, and the run root is created private below.
for auth in oauth_creds.json google_accounts.json installation_id settings.json projects.json; do
    copy_constant "$HOME/.gemini/$auth" ".gemini/$auth"
done
# The agy lane's real credential, and it is NOT `oauth_creds.json`. That file is the Gemini CLI's
# login; Antigravity keeps its own token one directory further down, and without it a run in an
# overridden HOME comes back in seconds with `"status":"ERROR","error":"authentication failed or
# timed out"` and its own log saying `You are not logged into Antigravity` - having spent nothing
# and produced no data point. Copied like every other credential, because a symlink would let a
# token refresh inside one run rewrite what every later run authenticates with.
copy_constant "$HOME/.gemini/antigravity-cli/antigravity-oauth-token" ".gemini/antigravity-cli/antigravity-oauth-token"
copy_constant "$HOME/.claude/.credentials.json" ".claude/.credentials.json"
# The codex lane's credential. Without it the run starts, reaches the model, and comes back in
# seconds having spent nothing - the same shape as the agy lane's missing Antigravity token.
copy_constant "$HOME/.codex/auth.json"          ".codex/auth.json"
copy_constant "$HOME/.config/zsh/secrets"       ".config/zsh/secrets"
copy_constant "$HOME/.config/gh"                ".config/gh"

chmod -R go-rwx "$root/$run_id"

# ---------------------------------------------------------------------------
# The state: present and empty, so a tool creates its store here and not in the real HOME.
# ---------------------------------------------------------------------------
mkdir -p "$run_home/.claude/projects"      # session transcripts
mkdir -p "$run_home/.claude/todos"
mkdir -p "$run_home/.codex/sessions"
mkdir -p "$run_home/.pi/agent/sessions"
mkdir -p "$run_home/.gemini/antigravity-cli/conversations"
mkdir -p "$run_home/.local/state"

# ai-memory is the one that matters. It writes and reads back, so run 1 records what it learned
# about the bead and run 7 starts ahead - contamination, not noise, and it favours whichever lane
# runs last. An empty store here is what keeps every run's first read empty.
mkdir -p "$run_home/.local/share/ai-memory"

# The MCP servers are removed rather than left configured: ai-memory would reconnect to the real
# store regardless of HOME if its path is absolute, and the web-reaching ones let a model find an
# answer instead of deriving one, which is a different capability than the one being priced.
if [ -f "$HOME/.claude.json" ]; then
    python3 - "$HOME/.claude.json" "$run_home/.claude.json" <<'PY'
import json, sys
src, dest = sys.argv[1], sys.argv[2]
with open(src) as handle:
    config = json.load(handle)
config.pop("mcpServers", None)
for project in config.get("projects", {}).values():
    if isinstance(project, dict):
        project.pop("mcpServers", None)
        project.pop("history", None)
with open(dest, "w") as handle:
    json.dump(config, handle, indent=2)
PY
    chmod go-rwx "$run_home/.claude.json"
fi

# ---------------------------------------------------------------------------
# Toolchain caches: SYMLINKED to the real ones, not copied and not left empty.
#
# These are the third thing that is neither a constant to copy nor state to isolate: they are
# machine infrastructure, they carry nothing about the bead from one run to the next, and they are
# far too large to duplicate. Leaving them empty is what the first pilot did, and it cost that run
# **357 MB of crates and 172 MB of npm packages re-downloaded inside the hour** - a large and
# unmeasured share of a wall clock that was then reported as the model's time. It also produced
# `error[E0463]: can't find crate`, which the agent reasonably wrote off as "a transient cargo
# issue" and worked around instead of the bead.
#
# A warm cache is a constant in the strict sense this experiment uses: identical for every lane,
# so it cancels in a comparison of lanes. An empty one is not - it is a tax the first run pays and
# the rest do not.
#
# Symlinked rather than copied, so a run reads the same 2.3 GB registry every other run reads.
# The consequence is that a run CAN write into the real cache, by downloading a crate that was not
# there. That is ordinary cargo behaviour against a shared CARGO_HOME, and a downloaded dependency
# carries no information about the bead, so it is not contamination in the sense that matters here.
# ---------------------------------------------------------------------------
link_cache() {
    local real="$HOME/$1"
    [ -e "$real" ] || return 0
    ln -s "$real" "$run_home/$1"
}

link_cache ".rustup"

# Go's two caches are split along the same line as cargo's, and the split falls out easier here.
#
#   the module cache (~/go/pkg/mod) is SHARED. Go writes its files read-only and verifies them
#   against go.sum, so the class of accident that cost a night on the cargo side - a run editing a
#   dependency in place and fixing the subject for every later build - takes a deliberate chmod
#   rather than an ordinary write. Re-downloading it per run would also need network the jail does
#   not have.
#
#   the build cache is PRIVATE, by doing nothing at all: with HOME pointed at the run, Go defaults
#   GOCACHE to $HOME/.cache/go-build and each run gets an empty one. Measured on the llmux subject,
#   a cold build plus its slowest test package is 22 s - paid inside the warm-up, outside the
#   measured window, and it buys the strongest isolation available: no compiled artifact from any
#   run can reach any other.
if [ -d "$HOME/go/pkg/mod" ]; then
    mkdir -p "$run_home/go/pkg"
    ln -s "$HOME/go/pkg/mod" "$run_home/go/pkg/mod"
fi

# npm gets the same split as cargo, but NOT for the reason this comment used to give.
#
# It claimed a race: `~/.npm` linked whole, a fresh sandbox's first `pi` bootstrapping through npx
# against a directory another run was already using, surfacing as `the model is NOT known inside the
# jail` about a catalog readable a minute later. The symptom was real and the cause was not. It was
# `verify.sh` piping a large catalogue into `grep -q` under `pipefail` - the quiet grep exits on the
# match, the writer takes SIGPIPE, and the gate reports the model missing BECAUSE it was found.
# Measured at 4 false rejections in 10 runs, and worse on a loaded machine, which is what made a
# check containing no concurrency look like contention between runs. The split below was written
# twice against that phantom; `evals/test_pipefail_grep.py` holds the real defect.
#
# The split stays, on the reason that was true all along and did not need a race: npm's bookkeeping
# is STATE, and state is what this file isolates. `_cacache` is the content-addressed store,
# immutable by construction and the expensive half, so it stays shared; everything else under
# `~/.npm` is rewritten by npm as it goes, so it is private per run.
if [ -d "$HOME/.npm" ]; then
    mkdir -p "$run_home/.npm"
    [ -d "$HOME/.npm/_cacache" ] && ln -s "$HOME/.npm/_cacache" "$run_home/.npm/_cacache"
fi

# ---------------------------------------------------------------------------
# CARGO_HOME is the exception, and it is split rather than linked whole.
#
# The reasoning above allowed a run to write into the shared cache, on the grounds that the only
# thing it can add is a crate it downloaded, and a downloaded dependency carries nothing about the
# bead. That is true of downloads and false of EDITS, and the difference cost a night.
#
# On 2026-08-15 a run read the bead - which says the fix belongs "at whatever reads the engine's
# `page_links` before a URL is built from it" - concluded correctly that this layer lives inside the
# `spider` crate, and patched the crate. Nine write calls into
# `~/.cargo/registry/src/…/spider-2.52.13/`, adding `html-escape` to its manifest and
# `decode_html_entities` to its `push_link`. It was a defensible reading of the task. It also fixed
# the subject bead for every later build on this machine, including the scorer's, so an untouched
# base tree began passing the canonical verification and the instrument looked broken rather than
# poisoned. Nothing about it appears in the diff being graded.
#
# So the split follows what is actually immutable:
#
#   registry/cache  - the downloaded .crate files, content-addressed and verified. SHARED, because
#                     re-downloading them is the 357 MB tax this whole section exists to avoid.
#   registry/index  - the resolver's metadata. SHARED for the same reason.
#   registry/src    - the EXTRACTED sources, which are ordinary writable files. PRIVATE per run.
#
# Cargo repopulates `src` from `cache` without touching the network, so the run pays an extraction
# and not a download, inside the warm-up and outside the measured window. A run may now edit its
# dependencies all it likes and take the consequences alone.
#
# The private `src` also removes the extraction race between concurrent runs structurally, since
# there is no longer one directory for two runs to unpack into.
if [ -d "$HOME/.cargo" ]; then
    mkdir -p "$run_home/.cargo/registry/src"
    for shared in bin config.toml credentials.toml env; do
        [ -e "$HOME/.cargo/$shared" ] && ln -s "$HOME/.cargo/$shared" "$run_home/.cargo/$shared"
    done
    for shared in cache index; do
        [ -d "$HOME/.cargo/registry/$shared" ] &&
            ln -s "$HOME/.cargo/registry/$shared" "$run_home/.cargo/registry/$shared"
    done
fi

# pi carries its OWN MCP configuration, beside its catalog rather than inside the Claude config
# handled above. Neutralising one and not the other leaves the memory server reachable for exactly
# the lane whose sessions this experiment reads, which is the worst place to leave it.
if [ -f "$HOME/.pi/agent/mcp.json" ]; then
    echo '{}' > "$run_home/.pi/agent/mcp.json"
fi

echo "$run_home"
