#!/usr/bin/env bash
# Bring up the sandbox network: an internal (routeless) network for the agent, plus a single
# allowlisting proxy that is the only way out.
#
# The agent container never gets a default route. It cannot reach github.com even by IP,
# because there is nothing to route through. The proxy is the one door and it is filtered.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NET_INTERNAL=wb-internal
NET_EGRESS=wb-egress
PROXY=wb-proxy

docker network inspect "$NET_INTERNAL" >/dev/null 2>&1 || \
  docker network create --internal "$NET_INTERNAL" >/dev/null
docker network inspect "$NET_EGRESS" >/dev/null 2>&1 || \
  docker network create "$NET_EGRESS" >/dev/null

docker rm -f "$PROXY" >/dev/null 2>&1 || true
docker build -q -t wb-proxy:local -f "$HERE/Dockerfile.proxy" "$HERE" >/dev/null

# tinyproxy sits on both networks: it can be reached from the routeless internal net, and it
# alone can reach the internet.
docker run -d --name "$PROXY" --network "$NET_INTERNAL" wb-proxy:local >/dev/null

docker network connect "$NET_EGRESS" "$PROXY"

echo "sandbox up: agent net=$NET_INTERNAL (no route out), proxy=$PROXY:8888"
