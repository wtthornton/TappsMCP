#!/usr/bin/env bash
# TappsMCP SubagentStop hook
# Advises on quality validation when subagent modified Python files.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
HAS_PY=$(echo "$INPUT" | "$PYBIN" -c "
import sys,json
try:
    d=json.load(sys.stdin)
    print('yes')
except Exception:
    print('no')
" 2>/dev/null)
if [ "$HAS_PY" = "yes" ]; then
  echo "Subagent completed. Run tapps_quick_check or tapps_validate_changed" >&2
  echo "on any Python files modified by this subagent." >&2
fi
exit 0
