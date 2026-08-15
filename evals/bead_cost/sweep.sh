#!/usr/bin/env bash
# Run rounds of bead-cost across several lanes, unattended, until a deadline.
#
# One run answers nothing. The measured relative standard deviation on turns was 44% on the
# ancestor experiment, and cost per completed bead divides by the runs that completed - both need N,
# and N is what an operator cannot supply by hand overnight. This is the thing that supplies it.
#
# WHAT IT DOES NOT DO: decide anything. Every run goes through `run.sh`, which gates the sandbox,
# warms the build outside the clock, scores and collects. A lane that cannot be reached is skipped
# and retried, never quietly dropped, because a lane missing from the results for an unrecorded
# reason is worse than one that failed loudly.
#
#   ./sweep.sh [<hours>]        default 8
#
# Stop it early by creating <root>/_sweep/STOP; the current round finishes and nothing new starts.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="${BEAD_COST_ROOT:-$HOME/tmp/bead-cost}"
hours="${1:-8}"
work="$root/_sweep"
mkdir -p "$work"

# awk rather than bc: bc is not installed on this machine, and a fractional `--hours 1.5` is worth
# supporting for a short supervised sweep.
deadline=$(awk -v now="$(date +%s)" -v h="$hours" 'BEGIN{printf "%d", now + h*3600}')
summary="$work/summary.tsv"
[ -s "$summary" ] || printf 'round\trun\tlane\tmodel\texit\tadmitted\tcommitted\twall_s\tinput\toutput\toutcome\n' >> "$summary"

# A warning stood here saying every verdict below was PROVISIONAL, because the canonical
# verification had stopped discriminating: three untouched base trees and one carrying a complete
# fix all scored alike. Both causes were found and closed the same day - one build directory shared
# by identical clones, and a run that patched the `spider` crate in the machine's cargo registry and
# thereby fixed the subject for every later build. Every affected run was re-scored from artefacts
# already on disk, so no run was paid for twice. The account is in
# `results/bead-cost/instrument-void-2026-08-15.md`, and it is worth reading before trusting any
# verdict recorded between 2026-08-14 23:00 and 2026-08-15 01:00. Rows outside that window are
# ordinary measurements.

# The roster. One entry per lane, and the account key is rotated per round rather than fixed: the
# limit on the Ollama lanes is a request RATE PER ACCOUNT, so two lanes running at once must sit on
# two different accounts, and no account should take every round in a row.
#
# Each lane also gets its own build directory. Per RUN it would be 4.5 GB apiece; per LANE it is
# three directories that stay warm, and warm is the correct state because the warm-up happens
# outside the measured window anyway.
lanes=(
    "agyflash|agy|gemini-3.7-flash-medium|"
    "kimi27|pi|litellm/kimi-k2.7|-k"
    "glm52|pi|litellm/glm-5.2|-k"
)

# Consecutive failures per lane. A lane is rested for one round after three in a row, then tried
# again: "unavailable" upstream is nearly always temporary, and a lane dropped for the night on the
# strength of three minutes of rate limiting is a hole in the results nobody can explain later.
declare -A strikes=()
declare -A resting=()

log() { printf '%s  %s\n' "$(date +%H:%M:%S)" "$1"; }

# Read one field out of a run's record, or `null`.
record_field() {
    python3 - "$1" "$2" <<'PY' 2>/dev/null || echo null
import json, pathlib, sys
path, dotted = pathlib.Path(sys.argv[1]), sys.argv[2]
if not path.exists():
    print("null"); raise SystemExit
node = json.loads(path.read_text())
for part in dotted.split("."):
    if not isinstance(node, dict) or part not in node:
        print("null"); raise SystemExit
    node = node[part]
print("null" if node is None else node)
PY
}

# Why a run failed, in the vocabulary the operator has to act on. Distinguishes the lane being
# unreachable from the model producing nothing, because they cost the same and mean the opposite.
lane_unreachable() {
    local run_dir="$1"
    grep -qiE "429|rate.?limit|quota|authentication failed|not logged in|no such model|not found" \
        "$run_dir/stderr.txt" "$run_dir/stdout.txt" 2>/dev/null
}

round=0
while [ "$(date +%s)" -lt "$deadline" ]; do
    if [ -e "$work/STOP" ]; then
        log "STOP file present - finishing without starting another round"
        break
    fi
    round=$((round + 1))
    log "=== round $round (deadline $(date -d "@$deadline" +%H:%M)) ==="

    started=()
    for entry in "${lanes[@]}"; do
        IFS='|' read -r name harness model keysuffix <<< "$entry"

        if [ -n "${resting[$name]:-}" ]; then
            log "$name is resting this round"
            unset "resting[$name]"
            continue
        fi

        # Rotate the account across rounds AND across lanes, so the two pi lanes never share one.
        model_for_round="$model"
        if [ -n "$keysuffix" ]; then
            slot=$(( (round + ${#started[@]}) % 3 + 1 ))
            model_for_round="${model}${keysuffix}${slot}"
        fi

        # Numbered from what is already on disk, not from this process's round counter. The counter
        # restarts at 1 on every relaunch, and the old collision handling appended a single `b`,
        # which collides again on the third attempt. The result was rounds that refused instantly,
        # each one still costing the lane a strike, so three lanes rested for failures that were
        # nothing but a repeated id.
        next=1
        for existing in "$root/$name"-*; do
            [ -d "$existing" ] || continue
            suffix="${existing##*-}"
            case "$suffix" in
                ''|*[!0-9]*) continue ;;
                *) [ "$((10#$suffix))" -ge "$next" ] && next=$((10#$suffix + 1)) ;;
            esac
        done
        run_id=$(printf '%s-%02d' "$name" "$next")

        log "launching $run_id  ($harness, $model_for_round)"
        CARGO_TARGET_DIR="/mnt/build/cargo-target-bead-cost/gen${BEAD_COST_BUILD_GEN:-2}/lane-$name" \
            "$here/run.sh" "$run_id" "$harness" "$model_for_round" \
            >> "$work/$run_id.log" 2>&1 &
        started+=("$!|$run_id|$name|$harness|$model_for_round")
    done

    [ ${#started[@]} -gt 0 ] || { log "every lane is resting; pausing 60s"; sleep 60; continue; }

    for item in "${started[@]}"; do
        IFS='|' read -r pid run_id name harness model_for_round <<< "$item"
        code=0
        wait "$pid" || code=$?
        run_dir="$root/$run_id"

        admitted=false
        if [ -s "$run_dir/verdict.json" ] &&
           python3 -c "
import json,sys
v=json.load(open('$run_dir/verdict.json'))
a=v.get('section_a') or {}
sys.exit(0 if v.get('scored') and a and all(a.values()) else 1)
" 2>/dev/null; then
            admitted=true
        fi

        committed=$(record_field "$run_dir/record.json" "worktree.committed")
        wall=""
        if [ -f "$run_dir/started_at" ] && [ -f "$run_dir/ended_at" ]; then
            wall=$(( $(date -d "$(cat "$run_dir/ended_at")" +%s) - $(date -d "$(cat "$run_dir/started_at")" +%s) ))
        fi
        input=$(record_field "$run_dir/record.json" "usage.input_tokens")
        output=$(record_field "$run_dir/record.json" "usage.output_tokens")

        outcome_for_row=$("$here/classify.py" "$run_dir" 2>/dev/null || echo broken)
        [ "$code" -ne 0 ] && outcome_for_row="broken"
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$round" "$run_id" "$name" "$model_for_round" "$code" "$admitted" \
            "$committed" "${wall:-null}" "$input" "$output" "$outcome_for_row" >> "$summary"

        outcome=$("$here/classify.py" "$run_dir" 2>/dev/null || echo broken)
        [ "$code" -ne 0 ] && outcome="broken"

        # A strike means THE LANE COULD NOT BE USED, never that the model got the bead wrong. The
        # first version counted any non-admission, which rests a lane for producing exactly the data
        # this sweep exists to collect - and rests it hardest when it is failing the task, which is
        # the case whose N matters most. Only unreachable and broken count.
        case "$outcome" in
            unreachable|broken)
                strikes[$name]=$(( ${strikes[$name]:-0} + 1 ))
                log "$run_id $outcome  (strike ${strikes[$name]} for $name)"
                if [ "${strikes[$name]}" -ge 3 ]; then
                    resting[$name]=1
                    strikes[$name]=0
                    log "$name rests one round after three consecutive unusable runs"
                fi
                ;;
            *)
                strikes[$name]=0
                log "$run_id $outcome  (${wall:-?}s)"
                ;;
        esac
    done
done

log "=== sweep finished after $round round(s) ==="
column -t -s "$(printf '\t')" "$summary" 2>/dev/null || cat "$summary"
