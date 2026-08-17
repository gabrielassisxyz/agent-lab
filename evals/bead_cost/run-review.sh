#!/usr/bin/env bash
# Drive the qualitative review: every reviewer, both passes, one command.
#
#   ./run-review.sh <packet-dir> [<out-dir>]
#   ./run-review.sh --probe <packet-dir> [<out-dir>]    one trivial call per reviewer, then stop
#   ./run-review.sh --pass-b <packet-dir> <out-dir>     the comparative pass alone, four calls
#
# `--pass-b` EXISTS TO MEASURE THE INSTRUMENT, not to save calls. Run against the SAME packet into a
# fresh output directory, it repeats the comparative pass with nothing changed - same entries, same
# lettering, same prompts, same flags, same GLM account - so every difference between the orderings
# it produces is the panel disagreeing with itself. Without that number, a position that moves
# between two runs cannot be told apart from a reviewer that was never stable to begin with, and
# there is no reading of "the arm varies" that survives not knowing which one it was.
#
# THE PROBE RUNS THROUGH THE SAME FUNCTIONS AS THE REAL PASSES, and that is the only reason it is
# worth anything. What fails on the first launch is never the prompt: it is a flag this CLI rejects,
# an account with no quota left, a credential the jail does not mount. A probe written as its own
# command line proves a command line nobody will run. This one asks each reviewer for its model id
# and for what it sees at `~/repositories/llmux`, so a single cheap call answers whether the
# reviewer works and whether it can reach the solution.
#
# WHY A SCRIPT. Eighteen calls across four different CLIs, each with its own trap - one waits on
# stdin forever without a redirect, one swallows the prompt if a flag comes after `--print`, one
# needs its account named or it bills whichever token a file happens to hold. Three of the pilot's
# five environment defects were steps run by hand in the wrong order or against the wrong path, and
# each was invisible until the numbers came back.
#
# THE PACKET GOES IN THE PROMPT, and that is the whole network story. It is under 30 KB, so no
# reviewer needs a tool to read anything, which means tools can be turned off wholesale rather than
# blocked one at a time. That is a stronger restriction than any web-specific flag, and the jail
# behind it makes the subject repository unreachable regardless.
#
# Every reviewer is asked to answer in JSON. `agy` is the only one that can be handed a schema, so
# the others are asked in the prompt and their output is repaired at aggregation time rather than
# trusted - a reviewer that wraps its object in prose has still answered.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
probe_only=0
pass_b_only=0
case "${1:-}" in
    --probe)  probe_only=1; shift ;;
    --pass-b) pass_b_only=1; shift ;;
esac
packet_dir="${1:?usage: run-review.sh [--probe|--pass-b] <packet-dir> [<out-dir>]}"
packet_dir="$(cd "$packet_dir" && pwd)"
# The answers live OUTSIDE the packet directory, and that is independence rather than tidiness.
# `agy` keeps its tools, and its calls run after the ones that answer earlier, so a default of
# `$packet_dir/answers` puts the other reviewers' rankings in a directory it can list. Four
# orderings that agree because one of them read the others are indistinguishable from four that
# agree because the signal is real, and agreement is what makes this result publishable. A sibling
# directory is not visible from inside the jail, and the answer files are opened by the unjailed
# caller regardless of where they sit.
out_dir="${2:-$(dirname "$packet_dir")/answers}"
mkdir -p "$out_dir"

review="$here/review"
[ -f "$packet_dir/packet.md" ] || { echo "run-review: no packet.md in $packet_dir" >&2; exit 1; }

# Refuse to run against a packet whose isolation has not been proven. The check is cheap and the
# failure it prevents is a reviewer that looked the answer up, which nothing in its output reveals.
if ! "$here/review-isolate.sh" "$packet_dir" >/dev/null 2>&1; then
    echo "run-review: isolation is NOT verified for $packet_dir - refusing to spend a reviewer on it" >&2
    exit 1
fi

CLAUDE_ACCOUNT="${BEAD_COST_CLAUDE_ACCOUNT:-bianca}"

stamp() { date '+%H:%M:%S'; }

# EVERY REVIEWER RUNS INSIDE THE JAIL THE CHECK ABOVE PROVED, and that is what the first version of
# this script got wrong: it verified the isolation and then invoked each CLI directly, so the check
# governed nothing. Per-CLI flags do not close the gap - `codex --sandbox read-only` restricts
# writes rather than reads, and `agy` has no tool restriction beyond `--sandbox`. Either could read
# the solution out of a copy of the subject repository and nothing in its written answer would show
# that it had.
#
# Redirections stay OUTSIDE this function on purpose. The prompt is expanded and the answer file
# opened by the unjailed caller, so neither has to live in the one directory the reviewer can see.
jailed() { "$here/review-isolate.sh" "$packet_dir" -- "$@"; }

# --- the four reviewers, each with the trap that would otherwise cost an hour -------------------

ask_codex() {  # <prompt-file> <out-file>
    # `< /dev/null` is not optional: `codex exec` waits on stdin forever without it, and the symptom
    # is a silent stall indistinguishable from a reviewer thinking hard. `--search` is NOT passed;
    # live web search is opt-in and stays off.
    jailed codex exec --skip-git-repo-check --sandbox read-only \
        -m gpt-5.6-sol -c model_reasoning_effort=medium \
        "$(cat "$1")" < /dev/null > "$2" 2>&1
}

ask_glm() {  # <prompt-file> <out-file> <account-slot>
    # `--no-tools` is the point: the packet is in the prompt, so a reviewer that can run nothing can
    # still answer, and cannot go looking for anything.
    #
    # The account is an ARGUMENT rather than a counter because the calls run in parallel lanes and a
    # counter incremented inside a background subshell is lost to its parent. Naming the slot where
    # the call is declared keeps the assignment deterministic, reproducible and greppable. The lane
    # limit here is a request rate PER ACCOUNT - the same reason the campaign's sweep rotates these
    # three keys - so calls that overlap must not share one.
    jailed pi -p --model "litellm/glm-5.2-k${3:-1}" --no-tools --no-session --no-extensions \
        --no-skills "$(cat "$1")" < /dev/null > "$2" 2>&1
}

ask_gemini() {  # <prompt-file> <out-file> <schema-file>
    # `--print` MUST be the last flag. With anything after it the prompt is swallowed and the model
    # politely answers about the flag instead. Effort is baked into the model id; `--effort` is
    # rejected for such ids. HOME is overridden so no GEMINI.md joins the context.
    local clean="$packet_dir/.agy-home"
    mkdir -p "$clean/.gemini"
    cp -r "$HOME/.gemini/antigravity-cli" "$clean/.gemini/" 2>/dev/null
    # `agy` opens the schema file itself, and it lives in this repository, which the jail does not
    # mount. Handed its original path it fails on a file it cannot see, so it is copied in beside
    # the packet. The schema only names the fields the prompt already asks for.
    local schema
    schema="$packet_dir/.schema-$(basename "$3")"
    cp "$3" "$schema"
    # `--dangerously-skip-permissions --mode plan` is the pair, and neither half works alone. In
    # print mode agy cannot prompt for a permission, so the first tool the model reaches for is
    # auto-denied and the turn ends having written nothing: status SUCCESS, response empty, the
    # answer gone. Measured twice on this prompt. Pre-authorising instead is a dead end - the
    # permission classes are per tool and which one gets used is the model's choice - and telling it
    # in the prompt that no tool would help did not stop it reaching for one.
    #
    # Auto-approving is only a small claim because of the two things around it: `--mode plan` cannot
    # write, and the jail leaves nothing to read but the packet. This is the case the jail was built
    # for, rather than an exception to it.
    jailed env HOME="$clean" agy --model=gemini-3.1-pro-high --disable-slash-commands --sandbox \
        --dangerously-skip-permissions --mode plan \
        --output-format=json --json-schema "$schema" --print-timeout 15m \
        --print "$(cat "$1")" > "$2" 2>&1
}

ask_opus() {  # <prompt-file> <out-file>
    # `claude-as` and never bare `claude`: file auth holds one account at a time, so a bare launch
    # runs against whichever account that file happens to carry and bills the wrong subscription.
    jailed env AGENT_SCOPE=1 claude-as "$CLAUDE_ACCOUNT" --model opus \
        --disallowedTools WebSearch WebFetch Bash Read Write Edit \
        -p "$(cat "$1")" < /dev/null > "$2" 2>&1
}

# A file that exists is not an answer. `agy` reports `"status":"SUCCESS"` with an empty `response`
# when a tool it wanted was auto-denied - a silent failure carrying a status field that says the
# opposite - and the envelope it writes around that emptiness is large enough that a size check
# calls it answered. Measured: a probe that asked for a directory listing came back SUCCESS, 574
# output tokens, and nothing to read. Left to the size check, a resumed run would skip that label
# for good and the aggregator would report a four-reviewer panel that had three.
#
# Which half of the envelope holds the answer is not fixed - agy has been seen putting the whole
# thing in `response` and putting an acknowledgement in `structured_output`, and the reverse - so
# emptiness has to mean BOTH are empty. Checking `response` alone would throw away a good answer.
answered() {  # <out-file>
    [ -s "$1" ] || return 1
    python3 - "$1" <<'PY'
import json, sys
text = open(sys.argv[1], errors="replace").read()
start = text.find("{")
if start < 0:
    sys.exit(0 if text.strip() else 1)     # not an envelope at all; any prose is an answer
try:
    env = json.loads(text[start:])
except ValueError:
    sys.exit(0)                            # prose around a broken object is repaired downstream
if not isinstance(env, dict) or "status" not in env:
    sys.exit(0)
filled = [v for v in (env.get("response"), env.get("structured_output")) if v]
sys.exit(0 if filled else 1)
PY
}

call() {  # <label> <reviewer-fn> <prompt-file> [<extra>]
    # `extra` is the reviewer-specific third argument: a schema path for agy, an account slot for
    # GLM. One slot rather than two named ones, because only ever one of them applies per reviewer.
    local label="$1" fn="$2" prompt="$3" extra="${4:-}"
    local out="$out_dir/$label.txt"
    if answered "$out"; then
        printf '%s  skip   %s (already answered)\n' "$(stamp)" "$label"
        return 0
    fi
    # A fan-out of eighteen paid calls is worth being able to read before it is worth running. This
    # prints what each lane would ask, with the account slot and schema it would pass, and spends
    # nothing: BEAD_COST_REVIEW_DRYRUN=1.
    if [ -n "${BEAD_COST_REVIEW_DRYRUN:-}" ]; then
        printf '%s  PLAN   %-18s %-11s %s\n' "$(stamp)" "$label" "$fn" "${extra:-<none>}"
        return 0
    fi
    printf '%s  ask    %s\n' "$(stamp)" "$label"
    if [ -n "$extra" ]; then "$fn" "$prompt" "$out" "$extra"; else "$fn" "$prompt" "$out"; fi
    if answered "$out"; then
        printf '%s  got    %s (%s bytes)\n' "$(stamp)" "$label" "$(wc -c < "$out")"
    else
        # Kept, not deleted: the empty envelope is the evidence of how it failed. Moved aside so a
        # rerun asks again instead of inheriting the emptiness.
        mv -f "$out" "$out.empty"
        printf '%s  EMPTY  %s - no answer in it; kept as %s.empty\n' "$(stamp)" "$label" "$label"
    fi
}

build_prompt() {  # <template> <body-file> <out>
    cat "$1" "$2" > "$3"
}

if [ "$probe_only" -eq 1 ]; then
    prompt_p="$out_dir/.prompt-probe.txt"
    cp "$review/prompt-probe.md" "$prompt_p"
    call "probe-codex"  ask_codex  "$prompt_p"
    call "probe-glm"    ask_glm    "$prompt_p"
    call "probe-gemini" ask_gemini "$prompt_p" "$review/schema-probe.json"
    call "probe-opus"   ask_opus   "$prompt_p"
    printf '%s  PROBE COMPLETE - read every answer before launching the real passes\n' "$(stamp)"
    exit 0
fi

# --- how the eighteen calls are spread ------------------------------------------------------------
#
# LANES, NOT A SCHEDULER. Each lane is a sequential worker over its own list, so the number of lanes
# a reviewer gets IS its concurrency cap and there is nothing to schedule, queue or tune. This
# script exists because three of the pilot's five environment defects were steps run by hand in the
# wrong order; replacing it with something clever enough to have its own bugs would undo the reason
# it was written.
#
# The caps, and where each comes from:
#   codex   2  - what its quota takes. It has the most calls, so it sets the wall-clock either way.
#   glm     1 per call, six at once - the limit is a request rate PER ACCOUNT and three accounts
#              absorb six calls at two apiece. The slot is named at the call, not counted at runtime.
#   agy     1  - its calls share one home directory under the packet and would collide in it.
#   claude  1  - file auth holds one account at a time.
#
# TWO WAVES, which is the design's only ordering rule: the blinding question is asked after the
# answers it must not influence are already on disk. Set BEAD_COST_REVIEW_SERIAL=1 to collapse every
# lane into one, which is the shape to reproduce in when a parallel run misbehaves.

lane() {  # reads "label|fn|prompt|extra" lines on stdin and works them in order
    local label fn prompt extra
    while IFS='|' read -r label fn prompt extra; do
        [ -n "$label" ] || continue
        call "$label" "$fn" "$prompt" "$extra"
    done
}

run_lanes() {  # <lane-body>...  one argument per lane, each a newline-separated list of specs
    local body pids=()
    if [ -n "${BEAD_COST_REVIEW_SERIAL:-}" ]; then
        for body in "$@"; do lane <<< "$body"; done
        return 0
    fi
    for body in "$@"; do
        lane <<< "$body" &
        pids+=("$!")
    done
    wait "${pids[@]}"
}

# Every prompt is built before anything is launched. Two lanes writing the same prompt file at the
# same moment is a race with nothing to gain from it.
letters=()
declare -A prompt_a=()
for impl in "$packet_dir"/impl-*.md; do
    letter="$(basename "$impl" .md)"; letter="${letter#impl-}"
    letters+=("$letter")
    prompt_a[$letter]="$out_dir/.prompt-a-$letter.txt"
    build_prompt "$review/prompt-pass-a.md" "$impl" "${prompt_a[$letter]}"
done
prompt_b="$out_dir/.prompt-b.txt"
build_prompt "$review/prompt-pass-b.md" "$packet_dir/packet.md" "$prompt_b"
prompt_c="$out_dir/.prompt-blinding.txt"
build_prompt "$review/prompt-blinding-check.md" "$packet_dir/packet.md" "$prompt_c"

# The four comparative calls, named once and used by both paths below, so a repeat run cannot drift
# from the run it is being compared against. The GLM account is pinned to the same slot for the same
# reason: an account is a variable, and this measurement has to have only one.
pass_b_lanes=(
    "passB-codex|ask_codex|$prompt_b|"
    "passB-glm|ask_glm|$prompt_b|1"
    "passB-gemini|ask_gemini|$prompt_b|$review/schema-pass-b.json"
    "passB-opus|ask_opus|$prompt_b|"
)

if [ "$pass_b_only" -eq 1 ]; then
    printf '%s  PASS B ALONE - 4 calls, identical to the ones in a full run\n' "$(stamp)"
    run_lanes "${pass_b_lanes[@]}"
    printf '%s  DONE - compare this ordering with the other runs of the same packet\n' "$(stamp)"
    exit 0
fi

# --- wave 1: pass A and pass B ---------------------------------------------------------------
#
# The comparative call heads codex's first lane deliberately. It is the half that carries the
# ranking, and putting it first means the answer worth reading arrives while the five absolute
# calls behind it are still running.

codex_queue=("${pass_b_lanes[0]}")
glm_queue=("${pass_b_lanes[1]}")
slot=1
for letter in "${letters[@]}"; do
    codex_queue+=("passA-$letter-codex|ask_codex|${prompt_a[$letter]}|")
    slot=$(( slot % 3 + 1 ))
    glm_queue+=("passA-$letter-glm|ask_glm|${prompt_a[$letter]}|$slot")
done

# Dealt round-robin into two lanes, so the first lane opens with pass B and the second with the
# first implementation, and neither ever runs more than one codex call at a time.
codex_lane_1=""; codex_lane_2=""
for i in "${!codex_queue[@]}"; do
    if [ $(( i % 2 )) -eq 0 ]; then
        codex_lane_1+="${codex_queue[$i]}"$'\n'
    else
        codex_lane_2+="${codex_queue[$i]}"$'\n'
    fi
done

glm_lanes=()
for spec in "${glm_queue[@]}"; do glm_lanes+=("$spec"); done

printf '%s  WAVE 1 - pass A and pass B, %s calls\n' "$(stamp)" "$(( ${#codex_queue[@]} + ${#glm_queue[@]} + 2 ))"
run_lanes "$codex_lane_1" "$codex_lane_2" "${glm_lanes[@]}" \
    "${pass_b_lanes[2]}" "${pass_b_lanes[3]}"

# --- wave 2: the blinding check, one call per reviewer ------------------------------------------

printf '%s  WAVE 2 - the blinding check, 4 calls\n' "$(stamp)"
run_lanes "blind-codex|ask_codex|$prompt_c|" \
    "blind-glm|ask_glm|$prompt_c|1" \
    "blind-gemini|ask_gemini|$prompt_c|$review/schema-blinding.json" \
    "blind-opus|ask_opus|$prompt_c|"

printf '%s  REVIEW COMPLETE - answers in %s\n' "$(stamp)" "$out_dir"
