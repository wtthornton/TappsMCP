#!/usr/bin/env bash
# Reap orphaned MCP serve processes (parent PID dead).
# Called by deploy-local (blue/green flip), NOT on git push or Cursor sessionStart.
# See docs/adr/0005-mcp-server-zombie-cleanup-hook-on-session-start.md

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

exec uv run python -m tapps_mcp.distribution.mcp_zombie_reap
