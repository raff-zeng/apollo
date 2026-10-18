#!/usr/bin/env bash
# Regenerate compile_commands.json for control/planning learning targets and
# rewrite it for host clangd.
#
#   tools/clangd/refresh.sh
#
# Bazel can only run inside the dev container, so this drives it through
# `docker exec`. Override the container name with APOLLO_CONTAINER.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTAINER="${APOLLO_CONTAINER:-apollo_dev_zrf}"
CONTAINER_USER="${APOLLO_CONTAINER_USER:-zrf}"

docker exec -u "$CONTAINER_USER" "$CONTAINER" \
  bash -lc "cd /apollo && bazel run //tools/clangd:refresh_compile_commands"

python3 "$ROOT/tools/clangd/normalize_compile_commands.py" \
  "$ROOT/compile_commands.json" "$ROOT"

"$ROOT/tools/clangd/sync_sysroot.sh"

echo "done: $ROOT/compile_commands.json"
