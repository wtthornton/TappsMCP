#!/usr/bin/env bash
# TappsMCP MCP zombie cleanup (Cursor sessionStart — ADR-0005 extension)
# Reaps orphaned nlt-* serve children (parent died). Safe with multiple Cursor windows.
set -euo pipefail
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

exit 0
