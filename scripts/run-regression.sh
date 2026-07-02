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

echo "[regression] Full non-slow suite (all packages, single invocation). Not part of git push." >&2
# TAP-4575: the three packages' tests are collected in one root pytest run
# (testpaths + --import-mode=importlib in pyproject.toml). No more per-package
# loop — a single invocation restores cross-package xdist parallelism.
if ! uv run pytest -m "not slow" -q --tb=line --timeout=60 "${XDIST[@]}" --maxfail=3; then
  echo "[regression] FAILED — investigate with: uv run pytest -m 'not slow' -v" >&2
  exit 1
fi

echo "[regression] OK" >&2
