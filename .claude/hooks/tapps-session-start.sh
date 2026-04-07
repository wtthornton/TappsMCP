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

echo "REQUIRED: Call tapps_session_start() NOW as your first action."
echo "This initializes project context for all TappsMCP quality tools."
echo "Tools called without session_start will have degraded accuracy."
echo "---"
echo "PIPELINE GATE: No Python edits should begin until session_start completes."
exit 0
