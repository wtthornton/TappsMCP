#!/usr/bin/env bash
# TappsMCP Memory Auto-Recall (Cursor — Epic 65.4)
# Injects relevant memories on sessionStart/preCompact. Graceful fallback: exit 0.
# ADR-0005 (Cursor multi-window): reap MCP serve processes whose parent died only.
# DO NOT add profile-global duplicate/stale reaping here — unsafe with N Cursor windows.
# See docs/adr/0005-mcp-server-zombie-cleanup-hook-on-session-start.md
if command -v ps &>/dev/null; then
    ORPHAN_PIDS=$(ps -eo pid=,ppid=,cmd= 2>/dev/null | while read -r pid ppid cmd_rest; do
        if printf '%s' "$cmd_rest" | grep -qE 'serve --profile nlt-|/(tapps-mcp|docsmcp|tapps-platform)( |$).*serve'; then
            if [ "$ppid" = "1" ] || ! kill -0 "$ppid" 2>/dev/null; then
                echo "$pid"
            fi
        fi
    done | sort -u | grep -E '^[0-9]+$' || true)
    if [ -n "$ORPHAN_PIDS" ]; then
        echo "[TappsMCP] Reaping orphaned MCP serve PIDs: $ORPHAN_PIDS" >&2
        echo "$ORPHAN_PIDS" | xargs kill 2>/dev/null || true
    fi
fi
INPUT=$(cat)
DEFAULT_QUERY="project context architecture"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
PY="import sys,json
try:
    d=json.load(sys.stdin)
    q=d.get('prompt','') or d.get('last_user_message','') or d.get('last_message','')
    if not q and 'messages' in d:
        ms=d.get('messages',[])
        if ms:
            last=ms[-1] if isinstance(ms[-1],dict) else {}
            q=last.get('content',last.get('text',''))
    if not q: q=d.get('context','') or '$DEFAULT_QUERY'
    q=(q or '')[:500]
    print(q)
except Exception:
    print('$DEFAULT_QUERY')
"
QUERY=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null || echo "$DEFAULT_QUERY")
if [ "$QUERY" != "$DEFAULT_QUERY" ] && [ ${#QUERY} -lt 50 ]; then
  exit 0
fi
PROJ_PY="import sys,json
try:
    d=json.load(sys.stdin)
    roots=d.get('workspace_roots') or []
    if roots:
        print(roots[0])
    elif d.get('cwd'):
        print(d['cwd'])
    else:
        print('.')
except Exception:
    print('.')
"
PROJECT_DIR=$(echo "$INPUT" | "$PYBIN" -c "$PROJ_PY" 2>/dev/null || echo ".")
TAPPS=$(command -v tapps-mcp 2>/dev/null)
if [ -z "$TAPPS" ]; then
  exit 0
fi
OUT=$("$TAPPS" memory recall --query "$QUERY" --project-root "$PROJECT_DIR" \
  --max-results 5 --min-score 0.3 --recall-key tapps-mcp-nlt-bundle-preference --recall-key tapps-mcp-nlt-memory-httpcore-fix 2>/dev/null)
if [ -n "$OUT" ]; then
  echo "$OUT"
fi
exit 0
