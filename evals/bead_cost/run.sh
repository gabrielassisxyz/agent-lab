#!/usr/bin/env bash
# Drive one bead-cost run end to end: build its environment, prove the environment, then measure.
#
# WHY a script rather than the copy-pasteable block the operations manual used to carry. Three of
# the pilot's five environment defects were steps that were skipped, reordered or run against the
# wrong path by hand - `verify.sh` pointed at a directory that was not the run's, a lane launched
# before its catalog existed, a ceiling chosen per invocation. Each was invisible until the numbers
# came back, and each cost a whole run. The order below is the part that has to be fixed:
#
#   base repo -> checkout -> sandbox -> prompt -> VERIFY -> warm the build -> measure
#
# Nothing is measured until `verify.sh` is green, and the build warms BEFORE the clock starts, so a
# cold compile is not billed to the model. That last one is the pilot's largest single distortion:
# 357 MB of crates and 172 MB of npm downloaded inside a measured hour and reported as the model's
# time.
#
#   ./run.sh <run-id> <harness> [<model>]   harness: pi | agy | claude | codex
#
# A LANE is the pair (harness, model): the same model through two harnesses is not one
# measurement, because one reports an envelope total and the other a per-turn sum. The two halves
# are therefore named apart everywhere, and only the records put them back together.
#
# Run it detached. A lane takes tens of minutes and a foreground invocation will hit the caller's
# own timeout long before the run finishes.
set -euo pipefail

run_id="${1:?usage: run.sh <run-id> <harness> [<model>]}"
harness="${2:?usage: run.sh <run-id> <harness> [<model>]   harness: pi | agy | claude | codex}"
model="${3:-}"

here="$(cd "$(dirname "$0")" && pwd)"
root="${BEAD_COST_ROOT:-$HOME/tmp/bead-cost}"
subject="${BEAD_COST_SUBJECT:-$HOME/repositories/archeion}"
bead="${BEAD_COST_BEAD:-arch-42q}"
# Two hours, and the reasoning matters more than the number: the pilot's one-hour ceiling killed a
# run four minutes from completion, twice. On a metered lane the tokens are already spent when the
# ceiling lands, so a low ceiling is the most expensive setting in the harness. `exit 124` is a
# failed run, never a slow model.
run_timeout="${BEAD_COST_TIMEOUT:-7200}"

case "$harness" in
    pi)     model="${model:-litellm/deepseek-v4-pro-max-k1}" ;;
    agy)    model="${model:-gemini-3.7-flash-medium}" ;;
    claude) model="${model:-sonnet}" ;;
    codex)  model="${model:-gpt-5.6-terra}" ;;
    *)      echo "run: unknown harness '$harness' (expected pi, agy, claude or codex)" >&2; exit 2 ;;
esac
# The claude lane runs under a named account's own token rather than whatever file-based auth
# happens to hold, because file auth carries one account at a time and a run against the wrong one
# starts normally and looks correct. `claude-as` refuses an unknown account instead of falling back.
claude_account="${BEAD_COST_CLAUDE_ACCOUNT:-primary}"
# Reasoning effort is a lane-defining setting on the codex harness and it is passed EXPLICITLY, not
# inherited. The machine's own `~/.codex/config.toml` carries one, that file is copied into the
# sandbox as a constant like every other config, and a value edited there between two rounds would
# move the arm without changing anything this experiment records. The same axis on the deepseek
# lanes was worth 2.2x in output tokens and the difference between 0 and 5 passes out of 5, so it
# is not a detail that can be left to whatever the machine happens to hold. What actually ran is
# read back out of the run's own trajectory by `collect.py`, rather than trusted from here.
codex_effort="${BEAD_COST_CODEX_EFFORT:-medium}"

run_dir="$root/$run_id"
run_home="$run_dir/home"
checkout="$run_dir/$(basename "$subject")"
# One target directory per run, exported rather than left to `bin/ci` to derive. bin/ci keys its
# default on the basename of the working directory, so an agent that creates its own worktree - which
# the global instruction files tell it to - would silently land on a second, cold target directory
# mid-run. Exporting it keeps the warm-up below and the run itself pointed at the same place.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/mnt/build/cargo-target-bead-cost/$run_id}"
# The agent's own worktrees have to land inside the run directory: that is the only part of the
# filesystem its jail can write, and `bin/worktree new` otherwise aims at ~/repositories/.worktrees,
# which is not mounted.
export WORKTREE_BASE="$run_dir/worktrees"

say() { printf '\n=== %s\n' "$1"; }

say "environment for $run_id ($harness, $model)"
# A run id is used once, and `checkout.sh` and `sandbox.sh` both enforce that so two runs are never
# mixed. An environment that was built and then never measured is a different case: `verify.sh`
# rejecting a sandbox is the gate working, and forcing a new id for it orphans ~100 MB and makes the
# id sequence lie about how many runs there were. `started_at` is what separates the two - it exists
# only once a lane has actually been launched.
if [ -f "$run_dir/started_at" ]; then
    echo "run: $run_id already ran (started_at exists). Pick another id." >&2
    exit 1
fi
# The base commit is passed rather than defaulted to the branch tip, because a bead whose work has
# already landed is cut from BEFORE it: the tip contains the answer. Left unset the tip is used,
# which is right for a bead nobody has done yet.
[ -d "$checkout" ] || "$here/checkout.sh" "$run_id" "${BEAD_COST_BASE_COMMIT:-}" >/dev/null
[ -d "$run_home" ] || "$here/sandbox.sh" "$run_id" >/dev/null
git -C "$checkout" rev-parse HEAD > "$run_dir/base_commit"
# The marker file keeps its historical name. Dozens of run directories on disk carry it, and
# re-collecting a verdict from artefacts already kept is how a metric gets repaired without paying
# for the runs again - which is worth more than a tidy filename.
echo "$harness" > "$run_dir/lane"
echo "$model" > "$run_dir/model"

# ---------------------------------------------------------------------------
# The prompt is built ONCE for the whole experiment and copied per run. Rebuilding it per run makes
# it a function of whatever `br` printed that day, and a comparison of lanes on prompts that differ
# by a byte is not a comparison.
# ---------------------------------------------------------------------------
shared_prompt="$root/_prompt-$bead.txt"
if [ ! -f "$shared_prompt" ]; then
    {
        echo "Solve this issue in the repository you are in. It is tracked as bead $bead."
        echo
        # Built from named fields rather than from `br show`'s rendering, and that is not tidiness.
        # A bead whose work has already landed is the normal case for a benchmark task - the base
        # tree is cut from before it, and the finished commit is what proves the task solvable - so
        # the tracker's record of that landing travels with the bead. On the first bead tried this
        # way the comment log read:
        #
        #     [2026-08-14 17:56 UTC] gabriel: Completed by <agent>. Implemented Reserve,
        #     PendingLease, and ReservationOutcome in …
        #
        # which hands over the identifiers the canonical verification demands, and says the work is
        # done. A run given that is not solving the bead. Whitelisting the fields is what makes the
        # leak impossible rather than filtered: a field nobody listed cannot reach the prompt, and
        # the next tracker version can add one without quietly widening what is sent.
        (cd "$subject" && br show "$bead" --json) | "$here/bead_prompt.py"
        echo
        echo "Make the change and commit it. The repository's gate is bin/ci."
    } > "$shared_prompt"
fi
cp "$shared_prompt" "$run_dir/prompt.txt"

# ---------------------------------------------------------------------------
# Everything from here to the end of the warm-up is serialized across concurrent runs, for the
# warm-up's sake: every run symlinks the machine's single ~/.cargo, so two warming together both
# unpack crate sources into one shared registry and the loser reads a tree the winner is still
# writing:
#
#     error: couldn't read .../registry/src/.../memchr-2.8.3/src/lib.rs: No such file or directory
#
# The verify step is inside the lock only because it sits between the two, and that is worth saying
# plainly because this comment used to claim otherwise. It read: three fresh sandboxes bootstrapping
# `pi` through npx within the same second made two lanes report `the model is NOT known inside the
# jail` about catalogs that were correct a minute later - a second cold-start race, in npm rather
# than cargo. **No such race exists.** That symptom was `verify.sh` piping a large catalogue into
# `grep -q` under `pipefail`: the quiet grep exits on the match, the writer takes SIGPIPE, and the
# gate reports the model missing precisely because it was found. It fails more often on a loaded
# machine, which is exactly how a check with no concurrency in it comes to look like contention.
# Two rewrites of the npm cache layout were aimed at that phantom before it was measured.
#
# Serializing the warm-up is outside the measured window, so it costs wall clock nobody is billed
# for. The lock is taken on a file descriptor rather than as
# `flock <file> <command>` because what has to be serialized is a shell function that needs the
# caller's exported environment.
mkdir -p "$root"
exec 9>"$root/.cold-start.lock"
flock 9

say "verifying the sandbox (nothing is measured until this is green)"
if ! BEAD_COST_CHECKOUT="$checkout" BEAD_COST_MODEL="$model" BEAD_COST_HARNESS="$harness" \
        "$here/verify.sh" "$run_home" > "$run_dir/verify.log" 2>&1; then
    flock -u 9
    echo "run: sandbox NOT verified - see $run_dir/verify.log" >&2
    grep -E "FAIL" "$run_dir/verify.log" >&2 || true
    exit 1
fi
grep -c "  ok " "$run_dir/verify.log" | xargs printf 'verify: %s gates ok\n'

# ai-jail decides what to bind from the dotdirs of the HOME it is launched with, so it always runs
# with the machine's HOME and the run's HOME is set for the process INSIDE. Handing ai-jail the run's
# HOME instead leaves the sandbox without ~/.cargo and without mise, which presents as a model that
# cannot build and a lane that does not exist.
jailed() {
    (cd "$checkout" && ai-jail --exec --no-save-config -- \
        env HOME="$run_home" WORKTREE_BASE="$WORKTREE_BASE" CARGO_TARGET_DIR="$CARGO_TARGET_DIR" "$@")
}

say "warming the build (outside the measured window, on purpose)"
warmed=0
# Chosen from the subject's own manifest rather than configured, because getting it wrong is silent:
# `cargo test --no-run` in a Go tree warms nothing, exits non-zero, and the run is rejected with a
# message about a tree that does not build.
if [ -f "$checkout/go.mod" ]; then
    # Two commands with different standing, and the split is the bead's doing rather than caution.
    #
    # `go build ./...` MUST succeed: that is the claim this step exists to make, that a run which
    # cannot build was handed a broken tree rather than a hard problem.
    #
    # Compiling the tests is best-effort, because on a bead whose canonical verification already
    # sits in the base tree naming a contract nothing implements yet, one test package failing to
    # compile IS the task. Requiring it would reject every run of exactly the bead being measured.
    # `-run` with a pattern matching nothing compiles them and executes none, so nothing here can
    # produce a result that looks like a verdict.
    jailed go build ./... > "$run_dir/prewarm.log" 2>&1 || warmed=1
    jailed go test -run '^$' ./... >> "$run_dir/prewarm.log" 2>&1 || true
else
    jailed cargo test --no-run --quiet > "$run_dir/prewarm.log" 2>&1 || warmed=1
fi
flock -u 9
exec 9>&-
if [ "$warmed" -ne 0 ]; then
    echo "run: the base tree does not build - that is the harness, not the model" >&2
    tail -20 "$run_dir/prewarm.log" >&2
    exit 1
fi

say "measuring"
date -Iseconds > "$run_dir/started_at"
set +e
case "$harness" in
    pi)
        # `< /dev/null` is not optional: a non-interactive agent that inherits a terminal stdin can
        # block forever, and the symptom is indistinguishable from thinking hard.
        jailed timeout "$run_timeout" pi -p \
            --model "$model" \
            --session-dir "$run_home/.pi/agent/sessions" \
            "$(cat "$run_dir/prompt.txt")" \
            < /dev/null > "$run_dir/stdout.txt" 2> "$run_dir/stderr.txt"
        ;;
    claude)
        # AGENT_SCOPE=1 is the documented way to tell `claude-as` that a scope is already provided:
        # without it the wrapper reaches for `systemd-run --user --scope`, which has no session bus
        # to talk to inside the jail. The run therefore loses the 6G MemoryHigh cap that an
        # interactive launch gets, which is acceptable for one agent and would not be for a swarm.
        jailed timeout "$run_timeout" env AGENT_SCOPE=1 claude-as "$claude_account" \
            --model "$model" \
            --dangerously-skip-permissions \
            --output-format json \
            -p "$(cat "$run_dir/prompt.txt")" \
            < /dev/null > "$run_dir/stdout.txt" 2> "$run_dir/stderr.txt"
        ;;
    codex)
        # `< /dev/null` is not optional: `codex exec` waits on stdin forever without it, and the
        # symptom is a silent stall indistinguishable from a model thinking hard.
        #
        # `--dangerously-bypass-approvals-and-sandbox` is the flag its own help reserves for
        # "environments that are externally sandboxed", which is exactly this one: the call already
        # runs inside ai-jail, whose mapping is the run's own worktree. Without it codex cannot
        # write, and a lane that cannot edit a file produces a no-diff that reads as a model failure.
        #
        # `mcp_servers={}` on the command line rather than an edited config: the copied
        # `config.toml` carries this machine's MCP servers, and ai-memory among them writes and
        # reads back, which is the contamination `sandbox.sh` exists to prevent. Overriding at the
        # call site keeps the copied config a copy.
        #
        # `--json` makes the usage readable. Without it the harness prints prose and the run's
        # token counts have to be recovered from the rollout alone.
        jailed timeout "$run_timeout" codex exec --json \
            -m "$model" \
            -c "model_reasoning_effort=\"$codex_effort\"" \
            -c 'mcp_servers={}' \
            --dangerously-bypass-approvals-and-sandbox \
            "$(cat "$run_dir/prompt.txt")" \
            < /dev/null > "$run_dir/stdout.txt" 2> "$run_dir/stderr.txt"
        ;;
    agy)
        # --print LAST, or agy answers about the flag that follows it instead of the prompt. Its own
        # --print-timeout defaults to five minutes and is a second ceiling that has to be raised
        # alongside the outer one.
        jailed timeout "$run_timeout" agy \
            --model="$model" \
            --dangerously-skip-permissions \
            --output-format=json \
            --print-timeout=110m \
            --print "$(cat "$run_dir/prompt.txt")" \
            < /dev/null > "$run_dir/stdout.txt" 2> "$run_dir/stderr.txt"
        ;;
esac
code=$?
set -e
echo "$code" > "$run_dir/exit_code"
date -Iseconds > "$run_dir/ended_at"
say "run finished with exit $code"

say "scoring"
# CARGO_TARGET_DIR is deliberately dropped here. The scorer keeps its own build directory so it
# never warms, or is warmed by, a run's build - and this script exports one for the run, which
# `score.sh` would otherwise inherit through its own `${CARGO_TARGET_DIR:-...}` default. Harmless
# for a single run and not harmless for a sweep, where several runs share one directory per slot
# and the scoring build would start landing in it.
# The scorer is per subject, because a verdict is a statement about one bead's canonical
# verification and nothing about it generalises: the fixture it vendors, the command that runs it
# and the shape of the verdict all differ. Chosen from the subject's manifest for the same reason
# the warm-up is.
scorer="$here/score.sh"
[ -f "$checkout/go.mod" ] && scorer="$here/score-go.sh"
env -u CARGO_TARGET_DIR "$scorer" "$checkout" "$run_id" "$run_dir" | tee "$run_dir/verdict.json"
"$here/collect.py" "$run_dir" --worktree "$("$here/find-work.sh" "$checkout" "$run_dir")" \
    > "$run_dir/record.json" || true
cat "$run_dir/record.json" 2>/dev/null || true
