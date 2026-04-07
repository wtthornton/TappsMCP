#!/usr/bin/env bash
# TappsMCP PostToolUse hook (Edit/Write)
# Fires after every Edit/Write and reminds to run quick_check for Python files.
INPUT=$(cat)
PY="import sys,json
d=json.load(sys.stdin)
ti=d.get('tool_input',{})
f=ti.get('file_path',ti.get('path',''))
if f.endswith('.py'): print(f)"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
FILE=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
if [ -n "$FILE" ]; then
  echo "[TappsMCP] Python file edited: $FILE"
  echo "ACTION REQUIRED: Run tapps_quick_check(\"$FILE\") before moving on."

  # Track edited Python files for validation-skip detection
  PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
  TAPPS_DIR="$PROJECT_DIR/.tapps-mcp"
  mkdir -p "$TAPPS_DIR"
  echo "$FILE" >> "$TAPPS_DIR/.edited-py-files"
  # Deduplicate
  if [ -f "$TAPPS_DIR/.edited-py-files" ]; then
    sort -u "$TAPPS_DIR/.edited-py-files" -o "$TAPPS_DIR/.edited-py-files" 2>/dev/null
  fi
fi
exit 0
