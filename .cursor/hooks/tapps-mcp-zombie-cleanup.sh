#!/usr/bin/env bash
# TappsMCP MCP zombie cleanup (Cursor sessionStart — ADR-0005 extension)
# Reaps orphaned nlt-* serve children after Reload Window so Cursor spawns a clean fleet.
set -euo pipefail
# ADR-0005: Kill stale MCP server processes to prevent zombie accumulation.
# Also reap project-.venv launches (missing httpx/httpcore) that break nlt-memory.
# DO NOT REMOVE — see docs/adr/0005-mcp-server-zombie-cleanup-hook-on-session-start.md
if command -v ps &>/dev/null && command -v awk &>/dev/null; then
    OLD_PIDS=$(ps -eo pid,etimes,cmd 2>/dev/null | \
        awk '$2 > 7200 && /tapps-mcp|docsmcp|tapps-platform/ && /serve/ {print $1}')
    VENV_PIDS=$(ps -eo pid,cmd 2>/dev/null | \
        awk '/\.venv\/bin\/(tapps-mcp|docsmcp|tapps-platform)/ && /serve/ {print $1}')
    NLT_DUP_PIDS=$(ps -eo pid,etimes,cmd 2>/dev/null | \
        awk '/serve --profile nlt-/ {
            pid=$1; age=$2;
            rest=$0;
            sub(/^.*serve --profile /, "", rest);
            sub(/ .*$/, "", rest);
            prof=rest;
            if (prof == "") next;
            if (!(prof in keeper)) {
                keeper[prof]=pid; youngest[prof]=age; dups[prof]="";
            } else if (age < youngest[prof]) {
                dups[prof]=dups[prof] " " keeper[prof];
                keeper[prof]=pid; youngest[prof]=age;
            } else {
                dups[prof]=dups[prof] " " pid;
            }
        }
        END {
            for (p in dups) {
                gsub(/^ /, "", dups[p]);
                if (dups[p] != "") print dups[p];
            }
        }') || NLT_DUP_PIDS=
    NLT_STALE_PIDS=$(ps -eo pid,etimes,cmd 2>/dev/null | \
        awk '$2 > 45 && /serve --profile nlt-/ {print $1}')
    ZOMBIE_PIDS=$({
    echo "$OLD_PIDS"
    echo "$VENV_PIDS"
    echo "$NLT_DUP_PIDS"
    echo "$NLT_STALE_PIDS"
    } | sort -u | grep -E '^[0-9]+$' || true)
    if [ -n "$ZOMBIE_PIDS" ]; then
        echo "[TappsMCP] Reaping stale MCP serve PIDs: $ZOMBIE_PIDS" >&2
        echo "$ZOMBIE_PIDS" | xargs kill 2>/dev/null || true
    fi
fi

exit 0
