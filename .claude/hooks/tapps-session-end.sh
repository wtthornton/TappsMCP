#!/usr/bin/env bash
# tapps-mcp-hook-version: 3.10.0
# TappsMCP SessionEnd hook (Epic 36.2)
# Creates a quality summary at session end.
# IMPORTANT: SessionEnd does NOT support exit code 2 (advisory only).
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
MARKER="$PROJECT_DIR/.tapps-mcp/.validation-marker"
if [ -f "$MARKER" ]; then
  echo "[TappsMCP] Session quality validated." >&2
else
  echo "[TappsMCP] Session ended without running quality validation." >&2
  echo "MUST run tapps_validate_changed before ending sessions." >&2
fi
exit 0
