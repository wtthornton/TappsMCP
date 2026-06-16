#!/usr/bin/env bash
# Upgrade TAPPS scaffolding + NLT MCP across consumer repos.
# Run from the tapps-mcp checkout after pulling latest master.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Override with your fleet, e.g.:
# export TAPPS_FLEET_ROOTS="$HOME/code/tapps-mcp,$HOME/code/AgentForge,$HOME/NewCompanyIdeas"
: "${TAPPS_FLEET_ROOTS:=}"

BUNDLE="${TAPPS_FLEET_BUNDLE:-developer}"
REINSTALL="${TAPPS_FLEET_REINSTALL_CLIS:-1}"
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
  esac
done

ARGS=(
  upgrade-fleet
  --tapps-checkout "$ROOT"
  --bundle "$BUNDLE"
  --uv-mode off
  --host auto
)
if [[ "$REINSTALL" == "1" ]]; then
  ARGS+=(--reinstall-clis)
fi
if [[ "$DRY_RUN" == "1" ]]; then
  ARGS+=(--dry-run)
fi

echo "==> Fleet upgrade (bundle=$BUNDLE, reinstall_clis=$REINSTALL — blue/green when reinstalling)"
if [[ -n "$TAPPS_FLEET_ROOTS" ]]; then
  ARGS+=(--roots "$TAPPS_FLEET_ROOTS")
  echo "    roots: $TAPPS_FLEET_ROOTS"
else
  ARGS+=(--scan-parent "${TAPPS_FLEET_SCAN_PARENT:-$HOME/code}")
  echo "    scan: ${TAPPS_FLEET_SCAN_PARENT:-$HOME/code}"
fi

uv run tapps-mcp "${ARGS[@]}"

echo ""
echo "Reload MCP in Cursor / Claude Code after deploy-local or fleet reinstall."
