#!/usr/bin/env bash
# Prove the sandbox holds, leak by leak. Run this before every experiment, not once.
#
# The rule this exists to serve: verify the artifact, never the exit code. "The container
# started" proves nothing. Each check below tries to perform the leak and asserts it FAILS.
#
#   usage: ./verify.sh <docker_image>
set -uo pipefail

IMG="${1:?usage: verify.sh <docker_image>}"
NET_INTERNAL=wb-internal
PROXY_URL="http://wb-proxy:8888"
pass=0; fail=0

check() { # check <description> <expect: ok|blocked> <command...>
  local desc="$1" expect="$2"; shift 2
  local out; out=$(docker run --rm --network "$NET_INTERNAL" \
    -e http_proxy="$PROXY_URL" -e https_proxy="$PROXY_URL" \
    -e HTTP_PROXY="$PROXY_URL" -e HTTPS_PROXY="$PROXY_URL" \
    --entrypoint bash "$IMG" -c "$*" 2>&1)
  local rc=$?
  if [[ "$expect" == "blocked" && $rc -ne 0 ]] || [[ "$expect" == "ok" && $rc -eq 0 ]]; then
    echo "  PASS  $desc"; ((pass++))
  else
    echo "  FAIL  $desc  (rc=$rc) $(echo "$out" | tail -1)"; ((fail++))
  fi
}

echo "== egress: the agent must not be able to read the answer =="
# The live leak found on 2026-07-14: the stock eval image reaches github.com (200). An agent
# with bash can fetch the upstream PR that fixes the issue instead of deriving the fix.
check "github.com is unreachable"         blocked "timeout 10 curl -sf -o /dev/null https://github.com"
check "GitHub API is unreachable"         blocked "timeout 10 curl -sf -o /dev/null https://api.github.com"
check "raw.githubusercontent unreachable" blocked "timeout 10 curl -sf -o /dev/null https://raw.githubusercontent.com"
check "PyPI is unreachable"               blocked "timeout 10 curl -sf -o /dev/null https://pypi.org"
check "google.com is unreachable"         blocked "timeout 10 curl -sf -o /dev/null https://google.com"
check "no default route out (raw IP)"     blocked "timeout 10 curl -sf -o /dev/null http://1.1.1.1"

echo "== the one door that must stay open =="
# pipefail-safe: this string runs in a fresh `bash -c` inside the container, which does not inherit
# this script's `pipefail`, so an early `grep -q` exit cannot turn a hit into a pipeline failure.
check "api.anthropic.com reachable via proxy" ok \
  "timeout 15 curl -s -o /dev/null -w '%{http_code}' https://api.anthropic.com/v1/messages | grep -qE '4[0-9]{2}'"

echo "== git: the fix must not be in the checkout =="
check "no git remotes"        ok "cd /testbed && [ -z \"\$(git remote -v)\" ]"
check "no branches or tags"   ok "cd /testbed && [ -z \"\$(git for-each-ref)\" ]"
# Every reachable commit must be an ancestor of HEAD (= base_commit). Any commit outside that
# set would be a future commit, i.e. the fix sitting in the agent's own object store.
check "no commits outside HEAD's ancestry" ok \
  "cd /testbed && [ \"\$(git rev-list --all --count)\" = \"\$(git rev-list HEAD --count)\" ]"

echo
echo "sandbox: $pass passed, $fail failed"
[ "$fail" -eq 0 ] || { echo "SANDBOX LEAKS — do not run an agent against this image."; exit 1; }
echo "sandbox holds."
