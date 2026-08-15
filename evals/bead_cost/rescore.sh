#!/usr/bin/env bash
# Re-grade runs that already happened, from the trees they left, and write the verdict back.
#
# This is the payoff for keeping raw artefacts instead of summaries. Twice now a verdict has been
# wrong for a reason that had nothing to do with the model - a scoring build directory shared across
# identical clones, and a dependency a run had patched inside the machine's cargo registry - and
# both times the repair was re-reading trees already on disk rather than paying for the runs again.
#
# It writes `verdict.json` back, which the hand re-scores did not, so the artefacts and the table
# stop disagreeing. A verdict that lives only in a terminal scrollback is one nobody can audit.
#
#   ./rescore.sh                 every run under the root that left a tree
#   ./rescore.sh <run-id> ...    only these
#
# Run the negative control first. Re-scoring against a poisoned environment just rewrites the
# artefacts with a new wrong answer, and this script cannot tell the difference.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="${BEAD_COST_ROOT:-$HOME/tmp/bead-cost}"
subject="${BEAD_COST_SUBJECT:-$HOME/repositories/archeion}"

if [ "$#" -gt 0 ]; then
    runs=("$@")
else
    runs=()
    for dir in "$root"/*/; do
        name=$(basename "$dir")
        case "$name" in _*) continue ;; esac
        [ -f "$dir/started_at" ] && runs+=("$name")
    done
fi

for run_id in "${runs[@]}"; do
    run_dir="$root/$run_id"
    checkout="$run_dir/$(basename "$subject")"
    if [ ! -d "$checkout" ]; then
        printf '%-16s skipped, no checkout\n' "$run_id"
        continue
    fi
    printf '%-16s ' "$run_id"
    # Written through a temporary file rather than redirected over the target: a scoring build that
    # dies halfway would otherwise leave an empty verdict behind, which reads as "the tree did not
    # build" about a tree that builds fine.
    if "$here/score.sh" "$checkout" "$run_id" "$run_dir" > "$run_dir/.verdict.next" 2>/dev/null &&
       [ -s "$run_dir/.verdict.next" ]; then
        mv "$run_dir/.verdict.next" "$run_dir/verdict.json"
        cat "$run_dir/verdict.json"
    else
        rm -f "$run_dir/.verdict.next"
        echo "FAILED to score - previous verdict left in place"
    fi
done
