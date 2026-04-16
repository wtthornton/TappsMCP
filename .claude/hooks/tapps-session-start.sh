#!/usr/bin/env bash
# TappsMCP SessionStart hook (startup/resume)
# Directs the agent to call tapps_session_start as the first MCP action.
# Writes a sidecar marker so downstream hooks can detect if session_start was called.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
TAPPS_DIR="$PROJECT_DIR/.tapps-mcp"
mkdir -p "$TAPPS_DIR"

# Clear stale session-start marker on fresh startup
rm -f "$TAPPS_DIR/.session-started"

# Kill MCP server processes older than 2 hours to prevent zombie accumulation.
# Claude Code spawns a new tapps-mcp/docsmcp process per session but never
# cleans them up — after several sessions this becomes a significant resource leak.
if command -v ps &>/dev/null && command -v awk &>/dev/null; then
    # Get PIDs of tapps-mcp/docsmcp processes older than 120 minutes.
    # Match on full command line ($0) because the executable is python3 and the
    # server name appears in later fields (e.g. "python3 /path/tapps-mcp serve").
    OLD_PIDS=$(ps -eo pid,etimes,cmd 2>/dev/null | \
        awk '$2 > 7200 && /tapps-mcp|docsmcp/ && /serve/ {print $1}')
    if [ -n "$OLD_PIDS" ]; then
        echo "$OLD_PIDS" | xargs kill 2>/dev/null || true
    fi
fi

echo "REQUIRED: Call tapps_session_start() NOW as your first action."
echo "This initializes project context for all TappsMCP quality tools."
echo "Tools called without session_start will have degraded accuracy."
echo "---"
echo "PIPELINE GATE: No Python edits should begin until session_start completes."
exit 0
