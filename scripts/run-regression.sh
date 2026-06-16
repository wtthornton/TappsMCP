#!/usr/bin/env bash
# Full non-slow regression — explicit opt-in; NOT run on git push.
#
# Usage:
#   scripts/run-regression.sh
#   scripts/run-regression.sh --serial   # skip pytest-xdist

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

XDIST=(-n auto)
if [[ "${1:-}" == "--serial" ]]; then
  XDIST=()
fi

echo "[regression] Full non-slow suite (all packages). Not part of git push." >&2
FAILED=0
for PKG in packages/tapps-mcp packages/tapps-core packages/docs-mcp; do
  echo "[regression] $PKG/tests/" >&2
  if ! uv run pytest "$PKG/tests/" -m "not slow" -q --tb=line --timeout=60 "${XDIST[@]}" --maxfail=3; then
    FAILED=1
  fi
done

if [[ "$FAILED" -ne 0 ]]; then
  echo "[regression] FAILED — investigate with: uv run pytest <pkg>/tests/ -m 'not slow' -v" >&2
  exit 1
fi

echo "[regression] OK" >&2
