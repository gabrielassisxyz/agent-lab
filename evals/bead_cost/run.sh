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
#   ./run.sh <run-id> <lane> [<model>]      lane: pi | agy
#
# Run it detached. A lane takes tens of minutes and a foreground invocation will hit the caller's
# own timeout long before the run finishes.
set -euo pipefail

run_id="${1:?usage: run.sh <run-id> <lane> [<model>]}"
lane="${2:?usage: run.sh <run-id> <lane> [<model>]   lane: pi | agy}"
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

case "$lane" in
    pi)  model="${model:-litellm/deepseek-v4-pro-max-k1}" ;;
    agy) model="${model:-gemini-3.7-flash-medium}" ;;
    *)   echo "run: unknown lane '$lane' (expected pi or agy)" >&2; exit 2 ;;
esac

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

say "environment for $run_id ($lane, $model)"
# A run id is used once, and `checkout.sh` and `sandbox.sh` both enforce that so two runs are never
# mixed. An environment that was built and then never measured is a different case: `verify.sh`
# rejecting a sandbox is the gate working, and forcing a new id for it orphans ~100 MB and makes the
# id sequence lie about how many runs there were. `started_at` is what separates the two - it exists
# only once a lane has actually been launched.
if [ -f "$run_dir/started_at" ]; then
    echo "run: $run_id already ran (started_at exists). Pick another id." >&2
    exit 1
fi
[ -d "$checkout" ] || "$here/checkout.sh" "$run_id" >/dev/null
[ -d "$run_home" ] || "$here/sandbox.sh" "$run_id" >/dev/null
git -C "$checkout" rev-parse HEAD > "$run_dir/base_commit"
echo "$lane" > "$run_dir/lane"
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
        (cd "$subject" && br show "$bead")
        echo
        echo "Make the change and commit it. The repository's gate is bin/ci."
    } > "$shared_prompt"
fi
cp "$shared_prompt" "$run_dir/prompt.txt"

# ---------------------------------------------------------------------------
# Everything from here to the end of the warm-up is serialized across concurrent runs, and both
# halves of that are paid for by a real failure.
#
# The warm-up: every run symlinks the machine's single ~/.cargo, so two warming together both unpack
# crate sources into one shared registry and the loser reads a tree the winner is still writing:
#
#     error: couldn't read .../registry/src/.../memchr-2.8.3/src/lib.rs: No such file or directory
#
# The check: the first `pi` invocation in a fresh sandbox bootstraps itself through npx against the
# same shared ~/.npm, and three of those starting within the same second made two lanes report
# `the model is NOT known inside the jail` about catalogs that were correct and are readable a
# minute later. Same failure shape, different cache, and it costs a whole round when the gate that
# is supposed to protect a run is the thing that fails.
#
# Both are cold-start effects and both are outside the measured window, so serializing them costs
# wall clock nobody is billed for. It is taken on a file descriptor rather than as
# `flock <file> <command>` because what has to be serialized is a shell function that needs the
# caller's exported environment.
mkdir -p "$root"
exec 9>"$root/.cold-start.lock"
flock 9

say "verifying the sandbox (nothing is measured until this is green)"
if ! BEAD_COST_CHECKOUT="$checkout" BEAD_COST_MODEL="$model" BEAD_COST_LANE="$lane" \
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
jailed cargo test --no-run --quiet > "$run_dir/prewarm.log" 2>&1 || warmed=1
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
case "$lane" in
    pi)
        # `< /dev/null` is not optional: a non-interactive agent that inherits a terminal stdin can
        # block forever, and the symptom is indistinguishable from thinking hard.
        jailed timeout "$run_timeout" pi -p \
            --model "$model" \
            --session-dir "$run_home/.pi/agent/sessions" \
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
env -u CARGO_TARGET_DIR "$here/score.sh" "$checkout" "$run_id" "$run_dir" | tee "$run_dir/verdict.json"
"$here/collect.py" "$run_dir" --worktree "$("$here/find-work.sh" "$checkout" "$run_dir")" \
    > "$run_dir/record.json" || true
cat "$run_dir/record.json" 2>/dev/null || true
