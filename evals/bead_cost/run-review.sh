#!/usr/bin/env bash
# Drive the qualitative review: every reviewer, both passes, one command.
#
#   ./run-review.sh <packet-dir> [<out-dir>]
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
packet_dir="${1:?usage: run-review.sh <packet-dir> [<out-dir>]}"
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

ask_glm() {  # <prompt-file> <out-file>
    # `--no-tools` is the point: the packet is in the prompt, so a reviewer that can run nothing can
    # still answer, and cannot go looking for anything.
    jailed pi -p --model litellm/glm-5.2-k1 --no-tools --no-session --no-extensions --no-skills \
        "$(cat "$1")" < /dev/null > "$2" 2>&1
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
    jailed env HOME="$clean" agy --model=gemini-3.1-pro-high --disable-slash-commands --sandbox \
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

call() {  # <label> <reviewer-fn> <prompt-file> [<schema>]
    local label="$1" fn="$2" prompt="$3" schema="${4:-}"
    local out="$out_dir/$label.txt"
    if [ -s "$out" ]; then
        printf '%s  skip   %s (already answered)\n' "$(stamp)" "$label"
        return 0
    fi
    printf '%s  ask    %s\n' "$(stamp)" "$label"
    if [ -n "$schema" ]; then "$fn" "$prompt" "$out" "$schema"; else "$fn" "$prompt" "$out"; fi
    printf '%s  got    %s (%s bytes)\n' "$(stamp)" "$label" "$(wc -c < "$out")"
}

build_prompt() {  # <template> <body-file> <out>
    cat "$1" "$2" > "$3"
}

# --- pass A: absolute, one implementation per call, by the two conflict-free reviewers ----------

for impl in "$packet_dir"/impl-*.md; do
    letter="$(basename "$impl" .md)"; letter="${letter#impl-}"
    prompt="$out_dir/.prompt-a-$letter.txt"
    build_prompt "$review/prompt-pass-a.md" "$impl" "$prompt"
    call "passA-$letter-codex" ask_codex "$prompt"
    call "passA-$letter-glm"   ask_glm   "$prompt"
done

# --- pass B: comparative, one packet, all four reviewers ----------------------------------------

prompt_b="$out_dir/.prompt-b.txt"
build_prompt "$review/prompt-pass-b.md" "$packet_dir/packet.md" "$prompt_b"
call "passB-codex"  ask_codex  "$prompt_b"
call "passB-glm"    ask_glm    "$prompt_b"
call "passB-gemini" ask_gemini "$prompt_b" "$review/schema-pass-b.json"
call "passB-opus"   ask_opus   "$prompt_b"

# --- the blinding check, asked AFTER the answers are on disk so it cannot influence them ---------

prompt_c="$out_dir/.prompt-blinding.txt"
build_prompt "$review/prompt-blinding-check.md" "$packet_dir/packet.md" "$prompt_c"
call "blind-codex"  ask_codex  "$prompt_c"
call "blind-glm"    ask_glm    "$prompt_c"
call "blind-gemini" ask_gemini "$prompt_c" "$review/schema-blinding.json"
call "blind-opus"   ask_opus   "$prompt_c"

printf '%s  REVIEW COMPLETE - answers in %s\n' "$(stamp)" "$out_dir"
