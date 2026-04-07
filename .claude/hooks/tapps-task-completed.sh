#!/usr/bin/env bash
# TappsMCP TaskCompleted hook
# Warns if validation was never run or Python files went unchecked.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
MARKER="$PROJECT_DIR/.tapps-mcp/.validation-marker"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
EDITED="$PROJECT_DIR/.tapps-mcp/.edited-py-files"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)

# Show validation results if available
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
    exit 0
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

# Warn about skipped validation
if [ -f "$EDITED" ] && [ ! -f "$MARKER" ]; then
  COUNT=$(wc -l < "$EDITED" 2>/dev/null | tr -d ' ')
  echo "WARNING: You skipped tapps_validate_changed." >&2
  echo "$COUNT Python file(s) were edited without quality validation:" >&2
  head -5 "$EDITED" | while read -r f; do echo "  - $f" >&2; done
  echo "Run tapps_validate_changed(file_paths=\"...\") before committing." >&2
elif [ ! -f "$MARKER" ]; then
  MSG="Reminder: run tapps_validate_changed to confirm quality."
  echo "$MSG" >&2
fi
exit 0
