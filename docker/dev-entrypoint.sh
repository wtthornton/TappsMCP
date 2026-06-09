#!/usr/bin/env bash
# Dev Docker entrypoint: uv sync when lockfiles change, then run tapps-mcp from workspace.
set -euo pipefail

cd /workspace

STAMP=".tapps-mcp/.docker-dev-sync.stamp"
needs_sync=0

if [[ ! -d .venv ]]; then
  needs_sync=1
fi

if [[ "$needs_sync" -eq 0 ]]; then
  for f in pyproject.toml uv.lock packages/tapps-core/pyproject.toml packages/tapps-mcp/pyproject.toml; do
    if [[ -f "$f" ]] && { [[ ! -f "$STAMP" ]] || [[ "$f" -nt "$STAMP" ]]; }; then
      needs_sync=1
      break
    fi
  done
fi

if [[ "$needs_sync" -eq 1 ]]; then
  echo "[dev-entrypoint] uv sync --all-packages (first start or deps changed)" >&2
  uv sync --all-packages --frozen 2>&1 | tail -8
  mkdir -p .tapps-mcp
  touch "$STAMP"
fi

exec uv run tapps-mcp "$@"
