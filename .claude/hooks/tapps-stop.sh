#!/usr/bin/env bash
# tapps-mcp-hook-version: 3.10.0
# TappsMCP Stop hook (HIGH engagement - BLOCKING on first invocation)
# Blocks if no quality validation was run this session.
# Reads sidecar for richer context when validation was run.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active','false'))"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
ACTIVE=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
MARKER="$PROJECT_DIR/.tapps-mcp/.validation-marker"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
if [ -f "$MARKER" ]; then
  # Emit sidecar summary if available
  if [ -f "$PROGRESS" ]; then
    "$PYBIN" -c "
import json
try:
    d=json.load(open('$PROGRESS'))
    if d.get('status')=='completed':
        t=d.get('total',0);p=sum(1 for r in d.get('results',[]) if r.get('gate_passed'))
        f=t-p;gp='all passed' if d.get('all_gates_passed') else f'{f} failed'
        print(f'Last validation: {t} files, {gp}')
except Exception:
    pass
" 2>/dev/null
  fi
  # Check report sidecar
  REPORT_PROGRESS="$PROJECT_DIR/.tapps-mcp/.report-progress.json"
  if [ -f "$REPORT_PROGRESS" ]; then
    REPORT_SUMMARY=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$REPORT_PROGRESS'))
    if d.get('status')=='completed':
        results=d.get('results',[])
        if results:
            avg=sum(r.get('score',0) for r in results)/len(results)
            print(f'Last report: {len(results)} files, avg {avg:.1f}/100')
except Exception:
    pass
" 2>/dev/null)
    [ -n "$REPORT_SUMMARY" ] && echo "$REPORT_SUMMARY"
  fi
  exit 0
fi
echo "BLOCKED: No quality validation was run this session." >&2
echo "Before declaring complete, run /tapps-finish-task (or tapps_validate_changed + tapps_checklist manually)." >&2
exit 2
