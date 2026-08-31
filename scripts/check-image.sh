#!/usr/bin/env bash
set -euo pipefail

image=mcp-server:local
docker run --rm --entrypoint /app/.venv/bin/python "${image}" \
  -c 'from mcp_server.server import mcp; assert mcp.name == "GrooveMap"'
test "$(docker run --rm --entrypoint /usr/bin/id "${image}" -u):$(docker run --rm --entrypoint /usr/bin/id "${image}" -g)" = "1000:1000"
test "$(docker image inspect "${image}" --format '{{ index .Config.Labels "org.opencontainers.image.title" }}')" = "mcp-server"
