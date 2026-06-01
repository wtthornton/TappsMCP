#!/usr/bin/env bash
# tapps-mcp-hook-version: 3.12.1
# TappsMCP SessionStart hook (startup/resume)
# Directs the agent to call tapps_session_start as the first MCP action.
# TAP-1379: Short-circuits on subsequent fires within the same Claude session
# (resume/compact re-fire the SessionStart hook; emitting the REQUIRED prompt
# every time caused agents to re-call tapps_session_start ~23x per session).
INPUT=$(cat)
SID=$(printf '%s' "$INPUT" | sed -n 's/.*"session_id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
SENTINEL_DIR="${TAPPS_PROJECT_ROOT:-.}/.tapps-mcp"
if [ -n "$SID" ]; then
  SENTINEL="$SENTINEL_DIR/.session-start-fired-$SID"
  if [ -f "$SENTINEL" ]; then
    # Already prompted the agent for this Claude session; stay silent on resume.
    exit 0
  fi
  mkdir -p "$SENTINEL_DIR" 2>/dev/null || true
  : > "$SENTINEL" 2>/dev/null || true
fi
# ADR-0005: Kill MCP server processes older than 2 hours to prevent zombie
# accumulation. Claude Code spawns a new tapps-mcp/docsmcp process per session
# but does not consistently reap old children — after several sessions this
# becomes a significant resource and Postgres connection leak.
# DO NOT REMOVE — see docs/adr/0005-mcp-server-zombie-cleanup-hook-on-session-start.md
if command -v ps &>/dev/null && command -v awk &>/dev/null; then
    OLD_PIDS=$(ps -eo pid,etimes,cmd 2>/dev/null | \
        awk '$2 > 7200 && /tapps-mcp|docsmcp/ && /serve/ {print $1}')
    if [ -n "$OLD_PIDS" ]; then
        echo "$OLD_PIDS" | xargs kill 2>/dev/null || true
    fi
fi
echo "REQUIRED: Call tapps_session_start() NOW as your first action."
echo "This initializes project context for all TappsMCP quality tools."
echo "Tools called without session_start will have degraded accuracy."
exit 0
