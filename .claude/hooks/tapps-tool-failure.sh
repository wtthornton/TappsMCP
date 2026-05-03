#!/usr/bin/env bash
# tapps-mcp-hook-version: 3.10.0
# TappsMCP PostToolUseFailure hook (Epic 36.3 / TAP-976)
# Logs TappsMCP MCP tool failures for diagnostics.
# IMPORTANT: PostToolUseFailure does NOT support exit code 2 (advisory only).
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
TOOL=$(echo "$INPUT" | "$PYBIN" -c "
import sys,json
d=json.load(sys.stdin)
print(d.get('tool_name',''))
" 2>/dev/null)
# Only log failures from TappsMCP tools — non-tapps failures stay silent.
case "$TOOL" in
  mcp__tapps-mcp__*|mcp__tapps_mcp__*) ;;
  *) exit 0 ;;
esac
ERROR=$(echo "$INPUT" | "$PYBIN" -c "
import sys,json
d=json.load(sys.stdin)
print(str(d.get('error','unknown error'))[:200])
" 2>/dev/null)
echo "TappsMCP tool $TOOL failed: $ERROR" >&2
echo "Run tapps_doctor to diagnose, or check MCP server connectivity." >&2
ROOT="${CLAUDE_PROJECT_DIR:-$PWD}"
mkdir -p "$ROOT/.tapps-mcp" 2>/dev/null
TS=$(date -u +%FT%TZ)
LINE=$(echo "$INPUT" | TS="$TS" TOOL="$TOOL" ERROR="$ERROR" "$PYBIN" -c "
import json, os, sys
print(json.dumps({
    'ts': os.environ.get('TS', ''),
    'tool': os.environ.get('TOOL', ''),
    'error': os.environ.get('ERROR', ''),
}, separators=(',', ':')))
" 2>/dev/null)
if [ -n "$LINE" ]; then
  echo "$LINE" >> "$ROOT/.tapps-mcp/.failure-log.jsonl" 2>/dev/null
fi
exit 0
