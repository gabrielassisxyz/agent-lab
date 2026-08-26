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
# `rw_maps` DOES NOT GOVERN EVERY MOUNT, and the first version of this script assumed it did.
# `ai-jail` binds some volumes regardless of the config - on this machine `/mnt/build`, where agent
# scratchpads live - and those scratchpads hold full clones of the subject repository. Only `mask`
# takes them away. See MASKED_VOLUMES below for the measurement.
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
if [ "${1:-}" = "--" ]; then shift; fi

packet_dir="$(cd "$packet_dir" && pwd)"
[ -f "$packet_dir/packet.md" ] || { echo "isolate: no packet.md in $packet_dir" >&2; exit 1; }

# Volumes `ai-jail` mounts READ-WRITE whatever `rw_maps` says, and that hold a copy of the subject
# repository. `/mnt/build` is where this machine keeps agent scratchpads, and two of them contain
# clones of llmux whose object store carries the commit this review uses as its hidden control.
# Measured from inside a jail this script had just certified as isolated: a sibling scratchpad
# listed, its clone's AGENTS.md read, and /mnt/build writable. `mask` replaces the path with an
# empty tmpfs and is the only lever that closed it.
#
# A CONTENT GREP IS NOT A SUBSTITUTE. The clone's HEAD sits on the base commit and the reference
# commit exists there only as a compressed object, so grepping the tree for the bead's symbols
# finds nothing while `git show` still hands over the answer.
MASKED_VOLUMES="/mnt/build"

# The packet cannot live inside a volume that has to be masked - masking it would take the packet
# with it. The agent scratchpad is under /mnt/build, so this is the ordinary case, not an exotic
# one, and refusing is better than building a jail whose contents are empty.
for volume in $MASKED_VOLUMES; do
    case "$packet_dir/" in
        "$volume"/*)
            echo "isolate: the packet is inside $volume, which must be masked - build it elsewhere" >&2
            echo "isolate: e.g. build_review_packet.py --out ~/tmp/bead-cost-review/review-packet" >&2
            exit 1 ;;
    esac
done

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

mask_toml=""
for volume in $MASKED_VOLUMES; do mask_toml="$mask_toml\"$volume\", "; done
mask_toml="${mask_toml%, }"

# Written to a temporary file and renamed into place, because this script now runs once per reviewer
# call and several of those overlap. A plain redirect truncates before it writes, so an `ai-jail`
# starting up in another call can read an empty config and fall back to its own defaults - which
# mount ~/repositories read-write, the exact hole this file exists to close, and nothing in the
# answer that reviewer writes would show that it happened. A rename is atomic within a filesystem:
# a reader sees the whole old file or the whole new one, never half of either.
jail_tmp="$packet_dir/.ai-jail.$$"
cat > "$jail_tmp" <<EOF
# Written by evals/bead_cost/review-isolate.sh. A reviewer sees this directory and nothing else.
#
# The default rw_maps is ~/repositories, which contains the subject repository and therefore the
# commit that solves the task under review. A reviewer that can read it is not forming a judgement,
# it is retrieving one.
command = ["claude"]
rw_maps = ["$packet_dir"]
ro_maps = []
hide_dotdirs = [".password-store"]
# Not cosmetic: these are mounted read-write regardless of rw_maps and carry clones of the subject.
mask = [$mask_toml]
no_docker = true
allow_tcp_ports = []
EOF
mv -f "$jail_tmp" "$packet_dir/.ai-jail"

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

    # A named list only ever closes the holes somebody thought of, and the /mnt/build leak was one
    # nobody had. This check is derived from the packet's own path instead: whatever else the jail
    # mounts, the directory holding the packet must show the packet and nothing beside it. It is the
    # only check here that would have caught that leak without already knowing the volume's name.
    siblings="$(jailed ls -A "$(dirname "$packet_dir")" 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')"
    if [ "$siblings" = "$(basename "$packet_dir")" ]; then
        echo "  ok    the packet has no visible siblings"
    else
        echo "  FAIL  the packet's neighbours are reachable: $siblings"; fail=1
    fi

    for volume in $MASKED_VOLUMES; do
        if [ -z "$(jailed ls -A "$volume" 2>/dev/null)" ]; then
            echo "  ok    $volume holds nothing inside the jail"
        else
            echo "  FAIL  $volume still has contents inside the jail; the mask did not take"; fail=1
        fi
    done

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

# The `cd` is the whole difference between a jail and a decoration, and it is not obvious enough to
# leave implicit: `ai-jail` reads `.ai-jail` from the CURRENT WORKING DIRECTORY, not from any path it
# is handed. Written as `ai-jail … -- env -C "$packet_dir" …` - which looks equivalent - it picks up
# whatever config the caller's directory has, mounts ~/repositories with it, and the subject
# repository is readable from inside a run that this very script has just certified as isolated.
# Measured both ways: without the cd, `ls ~/repositories/llmux` prints the tree; with it, "No such
# file or directory".
exec sh -c 'cd "$1" && shift && exec ai-jail --exec --no-save-config -- "$@"' _ "$packet_dir" "$@"
