#!/usr/bin/env bash
# Confine a qualitative reviewer to its packet, and PROVE the confinement from inside it.
#
#   ./review-isolate.sh <packet-dir>            write the jail config and verify it
#   ./review-isolate.sh <packet-dir> -- <cmd>   run a reviewer inside it
#
# WHAT THIS DOES AND DOES NOT PROMISE, because the honest version is narrower than "no network".
#
# The risk being closed is NOT the open web. The subject repository is private, so no search finds
# it. The risk is the local filesystem: `~/repositories/llmux` sits on this machine with the real
# solution in its history, and `ai-jail` mounts `~/repositories` READ-WRITE by default. A reviewer
# asked "which of these five is best" that can run `git log` in the subject repo is not reviewing,
# it is looking up the answer - and nothing in its written output would reveal that it had.
#
# So `rw_maps` is replaced with the packet directory alone. `~/repositories` is then not mounted at
# all rather than merely being impolite to read, which is the same fix `harden-worktree.sh` applies
# to a run for the same reason.
#
# `ai-jail` is a filesystem control and NOT a network control: `allow_tcp_ports` applies only in
# lockdown mode, and the reviewers must reach their own model endpoints or they cannot answer at
# all. Network restraint therefore has to come from each CLI's own flags, and the caller is
# responsible for passing them - they are listed in the plan beside each invocation. What this
# script guarantees is the part that can be guaranteed and checked: the answer key is not on the
# filesystem the reviewer can see.
set -euo pipefail

packet_dir="${1:?usage: review-isolate.sh <packet-dir> [-- <command>...]}"
shift || true
[ "${1:-}" = "--" ] && shift || true

packet_dir="$(cd "$packet_dir" && pwd)"
[ -f "$packet_dir/packet.md" ] || { echo "isolate: no packet.md in $packet_dir" >&2; exit 1; }

# The KEY names every lane. It lives beside the packet for decoding afterwards and must never be
# inside the jail, so it is moved out of the mounted directory rather than trusted to be ignored.
# It goes under ~/tmp, NOT beside the packet. The first attempt put it in the packet's parent
# directory and the check below reported it still reachable: a parent is not outside a mount whose
# path runs through it. Whether a location is inside the jail is a question to ask the jail.
key="$packet_dir/KEY-do-not-show-reviewers.json"
key_store="$HOME/tmp/bead-cost-review-keys"
if [ -f "$key" ]; then
    mkdir -p "$key_store"
    cp "$key" "$key_store/$(basename "$packet_dir").json"
    rm -f "$key"
    echo "isolate: key stored in $key_store, outside anything the jail mounts"
fi

cat > "$packet_dir/.ai-jail" <<EOF
# Written by evals/bead_cost/review-isolate.sh. A reviewer sees this directory and nothing else.
#
# The default rw_maps is ~/repositories, which contains the subject repository and therefore the
# commit that solves the task under review. A reviewer that can read it is not forming a judgement,
# it is retrieving one.
command = ["claude"]
rw_maps = ["$packet_dir"]
ro_maps = []
hide_dotdirs = [".password-store"]
mask = []
no_docker = true
allow_tcp_ports = []
EOF

jailed() { (cd "$packet_dir" && ai-jail --exec --no-save-config -- "$@"); }

if [ "$#" -eq 0 ]; then
    fail=0
    check() {  # <description> <expect-absent-path>
        if jailed test -e "$2" 2>/dev/null; then
            echo "  FAIL  $1 is REACHABLE from inside the jail ($2)"; fail=1
        else
            echo "  ok    $1 is not reachable from inside the jail"
        fi
    }
    echo "==> proving the isolation from INSIDE, not about it"
    check "the subject repository" "$HOME/repositories/llmux"
    check "every other repository"  "$HOME/repositories"
    check "the run root with all the other implementations" "$HOME/tmp/bead-cost"
    check "the decoding key" "$key_store"

    if jailed test -f "$packet_dir/packet.md" 2>/dev/null; then
        echo "  ok    the packet itself IS reachable"
    else
        echo "  FAIL  the packet is not reachable - the reviewer would have nothing to read"; fail=1
    fi

    # A negative control on the check itself. If `test -e` reported absence for something that is
    # certainly present, every line above would read "ok" while proving nothing.
    if jailed test -e "$packet_dir" 2>/dev/null; then
        echo "  ok    the check can distinguish present from absent"
    else
        echo "  FAIL  the check reports absence for the packet directory itself; it proves nothing"; fail=1
    fi

    if [ "$fail" -eq 0 ]; then
        echo "==> isolation verified"
        exit 0
    fi
    echo "==> ISOLATION NOT VERIFIED - do not launch a reviewer against this packet" >&2
    exit 1
fi

exec ai-jail --exec --no-save-config -- env -C "$packet_dir" "$@"
