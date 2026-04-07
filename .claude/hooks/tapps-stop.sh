#!/usr/bin/env bash
# TappsMCP Stop hook
# Checks if validation was run and warns about edited-but-unchecked Python files.
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
EDITED="$PROJECT_DIR/.tapps-mcp/.edited-py-files"

# Report validation status
if [ -f "$PROGRESS" ]; then
  SUMMARY=$("$PYBIN" -c "
import json
try:
    d=json.load(open('$PROGRESS'))
    if d.get('status')=='completed':
        t=d.get('total',0);p=sum(1 for r in d.get('results',[]) if r.get('gate_passed'))
        f=t-p;gp='all passed' if d.get('all_gates_passed') else f'{f} failed'
        print(f'Last validation: {t} files, {gp}')
except Exception:
    pass
" 2>/dev/null)
  if [ -n "$SUMMARY" ]; then
    echo "$SUMMARY" >&2
  fi
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
  [ -n "$REPORT_SUMMARY" ] && echo "$REPORT_SUMMARY" >&2
fi

# Warn if Python files were edited but validation never ran
if [ -f "$EDITED" ] && [ ! -f "$MARKER" ]; then
  COUNT=$(wc -l < "$EDITED" 2>/dev/null | tr -d ' ')
  echo "WARNING: $COUNT Python file(s) were edited but tapps_validate_changed was never run." >&2
  echo "Files: $(head -5 "$EDITED" | tr '\n' ', ')" >&2
  echo "Run tapps_validate_changed(file_paths=\"...\") before committing." >&2
elif [ ! -f "$MARKER" ]; then
  echo "Reminder: Run tapps_validate_changed before ending the session." >&2
fi
exit 0
