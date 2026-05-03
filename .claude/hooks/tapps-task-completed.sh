#!/usr/bin/env bash
# tapps-mcp-hook-version: 3.10.0
# TappsMCP TaskCompleted hook (HIGH engagement - BLOCKING)
# Blocks task completion if validation has not been run.
# Reads sidecar for richer context in systemMessage.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
MARKER="$PROJECT_DIR/.tapps-mcp/.validation-marker"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
if [ -f "$MARKER" ]; then
  AGE=$("$PYBIN" -c "
import time
try:
    t=float(open('$MARKER').read().strip())
    print(int(time.time()-t))
except Exception:
    print(9999)
" 2>/dev/null)
  if [ "${AGE:-9999}" -gt 3600 ]; then
    echo "BLOCKED: Validation marker is stale (>1h). Run tapps_validate_changed." >&2
    exit 2
  fi
  # Marker is fresh — emit sidecar summary if available
  if [ -f "$PROGRESS" ]; then
    "$PYBIN" -c "
import json
try:
    d=json.load(open('$PROGRESS'))
    if d.get('status')=='completed':
        t=d.get('total',0);p=sum(1 for r in d.get('results',[]) if r.get('gate_passed'))
        f=t-p;gp='all passed' if d.get('all_gates_passed') else f'{f} failed'
        print(f'Last validation: {t} files, {gp}')
        for r in d.get('results',[]):
            if not r.get('gate_passed'):
                print(f'  FAILED: {r["file"]} ({r.get("score","?")}/100)')
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
echo "BLOCKED: tapps_validate_changed has not been run." >&2
echo "Run it before completing this task." >&2
exit 2
