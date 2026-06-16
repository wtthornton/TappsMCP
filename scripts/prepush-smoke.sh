#!/usr/bin/env bash
# Fast serial smoke gate for git push — NOT a full regression suite.
# Full regression: scripts/run-regression.sh
#
# Intentionally avoids pytest-xdist (-n auto): parallel runs starve live Cursor
# MCP child processes during push and can flake unrelated integration tests.
#
# Each test path runs in its own pytest invocation to avoid conftest.py
# ImportPathMismatchError across packages.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SMOKE=(
  "packages/tapps-mcp/tests/unit/test_pre_push_hook_pipefail.py"
  "packages/tapps-mcp/tests/unit/test_audit_manifest.py::TestKeys"
  "packages/tapps-mcp/tests/unit/test_blue_green.py::TestFlipCurrent::test_atomic_flip"
  "packages/tapps-core/tests/unit/test_settings.py::TestProjectIdRootFallback::test_derives_slug_from_project_root_name"
  "packages/docs-mcp/tests/unit/test_scan_filters.py::TestBaselineExclude::test_venv_excluded"
)

echo "[prepush-smoke] Running ${#SMOKE[@]} curated tests (serial, no xdist)..." >&2
for _TEST in "${SMOKE[@]}"; do
  uv run pytest "$_TEST" -q --tb=line --timeout=60
done
