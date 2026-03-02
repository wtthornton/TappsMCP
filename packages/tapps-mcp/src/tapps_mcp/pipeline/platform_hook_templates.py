"""Hook script templates and configuration for Claude Code and Cursor.

Contains all shell/PowerShell hook script strings and their JSON config
mappings. Extracted from ``platform_generators.py`` to reduce file size.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Claude Code hook script templates (Story 12.5)
# ---------------------------------------------------------------------------

CLAUDE_HOOK_SCRIPTS: dict[str, str] = {
    "tapps-session-start.sh": """\
#!/usr/bin/env bash
# TappsMCP SessionStart hook (startup/resume)
# Directs the agent to call tapps_session_start as the first MCP action.
INPUT=$(cat)
echo "REQUIRED: Call tapps_session_start() NOW as your first action."
echo "This initializes project context for all TappsMCP quality tools."
echo "Tools called without session_start will have degraded accuracy."
exit 0
""",
    "tapps-session-compact.sh": """\
#!/usr/bin/env bash
# TappsMCP SessionStart hook (compact)
# Re-injects TappsMCP context after context compaction.
INPUT=$(cat)
echo "[TappsMCP] Context was compacted — re-injecting TappsMCP awareness."
echo "Remember: use tapps_quick_check after editing Python files."
echo "Run tapps_validate_changed before declaring work complete."
exit 0
""",
    "tapps-post-edit.sh": """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook (Edit/Write)
# Reminds the agent to run quality checks after file edits.
INPUT=$(cat)
PY="import sys,json
d=json.load(sys.stdin)
ti=d.get('tool_input',{})
f=ti.get('file_path',ti.get('path',''))
if f.endswith('.py'): print(f)"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
FILE=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
if [ -n "$FILE" ]; then
  echo "Python file edited: $FILE"
  echo "Consider running tapps_quick_check on it."
fi
exit 0
""",
    "tapps-stop.sh": """\
#!/usr/bin/env bash
# TappsMCP Stop hook
# Reminds to run tapps_validate_changed but does NOT block.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active','false'))"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
ACTIVE=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
echo "Reminder: Run tapps_validate_changed before ending the session." >&2
exit 0
""",
    "tapps-task-completed.sh": """\
#!/usr/bin/env bash
# TappsMCP TaskCompleted hook
# Reminds to run quality checks but does NOT block.
INPUT=$(cat)
MSG="Reminder: run tapps_validate_changed to confirm quality."
echo "$MSG" >&2
exit 0
""",
    "tapps-pre-compact.sh": """\
#!/usr/bin/env bash
# TappsMCP PreCompact hook
# Backs up scoring context before context window compaction.
INPUT=$(cat)
BACKUP_DIR="${CLAUDE_PROJECT_DIR:-.}/.tapps-mcp"
mkdir -p "$BACKUP_DIR"
echo "$INPUT" > "$BACKUP_DIR/pre-compact-context.json"
echo "[TappsMCP] Scoring context backed up to $BACKUP_DIR/pre-compact-context.json"
exit 0
""",
    "tapps-subagent-start.sh": """\
#!/usr/bin/env bash
# TappsMCP SubagentStart hook
# Injects TappsMCP awareness into spawned subagents.
INPUT=$(cat)
echo "[TappsMCP] This project uses TappsMCP for code quality."
echo "MCP tools: tapps_quick_check, tapps_score_file, tapps_validate_changed, tapps_memory."
exit 0
""",
    "tapps-subagent-stop.sh": """\
#!/usr/bin/env bash
# TappsMCP SubagentStop hook (Epic 36.1)
# Advises on quality validation when subagent modified Python files.
# IMPORTANT: SubagentStop does NOT support exit code 2 (advisory only).
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
# Check for Python file modifications (best-effort)
HAS_PY=$(echo "$INPUT" | "$PYBIN" -c "
import sys,json
try:
    d=json.load(sys.stdin)
    # SubagentStop event may include changed files info
    print('yes')
except Exception:
    print('no')
" 2>/dev/null)
if [ "$HAS_PY" = "yes" ]; then
  echo "Subagent completed. Run tapps_quick_check or tapps_validate_changed" >&2
  echo "on any Python files modified by this subagent." >&2
fi
exit 0
""",
    "tapps-session-end.sh": """\
#!/usr/bin/env bash
# TappsMCP SessionEnd hook (Epic 36.2)
# Creates a quality summary at session end.
# IMPORTANT: SessionEnd does NOT support exit code 2 (advisory only).
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
MARKER="$PROJECT_DIR/.tapps-mcp/.validation-marker"
if [ -f "$MARKER" ]; then
  echo "[TappsMCP] Session quality validated." >&2
else
  echo "[TappsMCP] Session ended without running quality validation." >&2
  echo "Consider running tapps_validate_changed before ending sessions." >&2
fi
exit 0
""",
    "tapps-tool-failure.sh": """\
#!/usr/bin/env bash
# TappsMCP PostToolUseFailure hook (Epic 36.3)
# Logs TappsMCP MCP tool failures for diagnostics.
# IMPORTANT: PostToolUseFailure does NOT support exit code 2 (advisory only).
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
TOOL=$(echo "$INPUT" | "$PYBIN" -c "
import sys,json
d=json.load(sys.stdin)
print(d.get('tool_name',''))
" 2>/dev/null)
# Only log failures from TappsMCP tools
case "$TOOL" in
  mcp__tapps-mcp__*|mcp__tapps_mcp__*)
    ERROR=$(echo "$INPUT" | "$PYBIN" -c "
import sys,json
d=json.load(sys.stdin)
print(d.get('error','unknown error')[:200])
" 2>/dev/null)
    echo "TappsMCP tool $TOOL failed: $ERROR" >&2
    echo "Check MCP server connectivity and configuration." >&2
    ;;
esac
exit 0
""",
    "tapps-pre-bash.sh": """\
#!/usr/bin/env bash
# TappsMCP PreToolUse hook (Bash) - destructive command guard (opt-in)
# Blocks commands containing rm -rf, format c:, etc. Exit 2 = block, 0 = allow.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
CMD=$(echo "$INPUT" | "$PYBIN" -c "
import sys, json
try:
    d = json.load(sys.stdin)
    ti = d.get('tool_input', {}) or {}
    cmd = ti.get('command', '') or ti.get('cmd', '')
    if not cmd and isinstance(ti.get('args'), list):
        cmd = ' '.join(str(a) for a in ti['args'])
    print(cmd if isinstance(cmd, str) else '')
except Exception:
    print('')
" 2>/dev/null)
# Blocklist (substring match, case-insensitive for format/del)
BLOCK=0
case "$CMD" in
  *rm\ -rf*|*rm\ -fr*|*rm\ -r\ -f*|*rm\ -rf\ /*) BLOCK=1 ;;
  *format\ c:*|*format\ c:/*|*format\ C:*|*format\ C:/*) BLOCK=1 ;;
  *del\ /f\ /s\ /q*|*del\ /s\ /q*|*rd\ /s\ /q*) BLOCK=1 ;;
  *:(){*:\|:&*}\;:*) BLOCK=1 ;;
esac
if [ "$BLOCK" = 1 ]; then
  echo "TappsMCP: Blocked potentially destructive command." >&2
  exit 2
fi
exit 0
""",
    "tapps-memory-capture.sh": """\
#!/usr/bin/env bash
# TappsMCP Stop hook - Memory Capture (Epic 34.5)
# Writes session quality data to .tapps-mcp/session-capture.json for
# persistence into shared memory on next session start.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
ACTIVE=$(echo "$INPUT" | "$PYBIN" -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active','false'))" \
  2>/dev/null)
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
CAPTURE_DIR="$PROJECT_DIR/.tapps-mcp"
MARKER="$CAPTURE_DIR/.validation-marker"
VALIDATED="false"
if [ -f "$MARKER" ]; then
  VALIDATED="true"
fi
DATE=$("$PYBIN" -c "from datetime import date; print(date.today().isoformat())" 2>/dev/null \
  || date +%Y-%m-%d 2>/dev/null || echo "unknown")
FILES=$("$PYBIN" -c \
  "import subprocess,sys;r=subprocess.run(['git','diff','--name-only','HEAD'],capture_output=True,text=True,cwd='$PROJECT_DIR');print(len([f for f in r.stdout.strip().split(chr(10)) if f.endswith('.py') and f]))" \
  2>/dev/null || echo "0")
mkdir -p "$CAPTURE_DIR" 2>/dev/null || exit 0
"$PYBIN" -c "
import json,sys
data={'date':'$DATE','validated':$VALIDATED,'files_edited':int('$FILES' or '0')}
with open('$CAPTURE_DIR/session-capture.json','w') as f:
    json.dump(data,f)
" 2>/dev/null
exit 0
""",
}

# ---------------------------------------------------------------------------
# Claude Code hook script templates - PowerShell (Windows)
# ---------------------------------------------------------------------------

CLAUDE_HOOK_SCRIPTS_PS: dict[str, str] = {
    "tapps-session-start.ps1": """\
# TappsMCP SessionStart hook (startup/resume)
# Directs the agent to call tapps_session_start as the first MCP action.
$null = $input | Out-Null
Write-Output "REQUIRED: Call tapps_session_start() NOW as your first action."
Write-Output "This initializes project context for all TappsMCP quality tools."
Write-Output "Tools called without session_start will have degraded accuracy."
exit 0
""",
    "tapps-session-compact.ps1": """\
# TappsMCP SessionStart hook (compact)
# Re-injects TappsMCP context after context compaction.
$null = $input | Out-Null
Write-Output "[TappsMCP] Context was compacted - re-injecting TappsMCP awareness."
Write-Output "Remember: use tapps_quick_check after editing Python files."
Write-Output "Run tapps_validate_changed before declaring work complete."
exit 0
""",
    "tapps-post-edit.ps1": """\
# TappsMCP PostToolUse hook (Edit/Write)
# Reminds the agent to run quality checks after file edits.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $file = if ($data.tool_input.file_path) { $data.tool_input.file_path }
            elseif ($data.tool_input.path) { $data.tool_input.path }
            else { "" }
} catch {
    $file = ""
}
if ($file -and $file -match '\\.py$') {
    Write-Output "Python file edited: $file"
    Write-Output "Consider running tapps_quick_check on it."
}
exit 0
""",
    "tapps-stop.ps1": """\
# TappsMCP Stop hook
# Reminds to run tapps_validate_changed but does NOT block.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $active = $data.stop_hook_active
} catch {
    $active = $false
}
if ($active -eq $true -or $active -eq "true" -or $active -eq "True") {
    exit 0
}
Write-Host "Reminder: Run tapps_validate_changed before ending the session." -ForegroundColor Yellow
exit 0
""",
    "tapps-task-completed.ps1": """\
# TappsMCP TaskCompleted hook
# Reminds to run quality checks but does NOT block.
$null = $input | Out-Null
Write-Host "Reminder: run tapps_validate_changed to confirm quality." -ForegroundColor Yellow
exit 0
""",
    "tapps-pre-compact.ps1": """\
# TappsMCP PreCompact hook
# Backs up scoring context before context window compaction.
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
$backupDir = if ($projDir) { "$projDir/.tapps-mcp" } else { ".tapps-mcp" }
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}
$outFile = "$backupDir/pre-compact-context.json"
$rawInput | Set-Content -Path $outFile -Encoding UTF8
Write-Output "[TappsMCP] Scoring context backed up to $outFile"
exit 0
""",
    "tapps-subagent-start.ps1": """\
# TappsMCP SubagentStart hook
# Injects TappsMCP awareness into spawned subagents.
$null = $input | Out-Null
Write-Output "[TappsMCP] This project uses TappsMCP for code quality."
Write-Output "MCP tools: tapps_quick_check, tapps_score_file, tapps_validate_changed, tapps_memory."
exit 0
""",
    "tapps-subagent-stop.ps1": """\
# TappsMCP SubagentStop hook (Epic 36.1)
# Advises on quality validation when subagent modified Python files.
# IMPORTANT: SubagentStop does NOT support exit code 2 (advisory only).
$rawInput = @($input) -join "`n"
$msg = "Subagent completed. Run tapps_quick_check or tapps_validate_changed"
Write-Host $msg -ForegroundColor Yellow
$msg2 = "on any Python files modified by this subagent."
Write-Host $msg2 -ForegroundColor Yellow
exit 0
""",
    "tapps-session-end.ps1": """\
# TappsMCP SessionEnd hook (Epic 36.2)
# Creates a quality summary at session end.
# IMPORTANT: SessionEnd does NOT support exit code 2 (advisory only).
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$marker = "$projDir/.tapps-mcp/.validation-marker"
if (Test-Path $marker) {
    Write-Host "[TappsMCP] Session quality validated." -ForegroundColor Green
} else {
    $msg = "[TappsMCP] Session ended without running quality validation."
    Write-Host $msg -ForegroundColor Yellow
    $msg2 = "Consider running tapps_validate_changed before ending sessions."
    Write-Host $msg2 -ForegroundColor Yellow
}
exit 0
""",
    "tapps-tool-failure.ps1": """\
# TappsMCP PostToolUseFailure hook (Epic 36.3)
# Logs TappsMCP MCP tool failures for diagnostics.
# IMPORTANT: PostToolUseFailure does NOT support exit code 2 (advisory only).
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $tool = if ($data.tool_name) { $data.tool_name } else { "" }
} catch {
    $tool = ""
}
if ($tool -match '^mcp__tapps[-_]mcp__') {
    $err = if ($data.error) { $data.error } else { "unknown error" }
    $error_msg = $err.Substring(0, [Math]::Min(200, $err.Length))
    Write-Host "TappsMCP tool $tool failed: $error_msg" -ForegroundColor Red
    Write-Host "Check MCP server connectivity and configuration." -ForegroundColor Yellow
}
exit 0
""",
    "tapps-pre-bash.ps1": """\
# TappsMCP PreToolUse hook (Bash) - destructive command guard (opt-in)
# Blocks commands containing rm -rf, format c:, etc. Exit 2 = block, 0 = allow.
$raw = @($input) -join "`n"
$cmd = ""
try {
    $data = $raw | ConvertFrom-Json
    $ti = $data.tool_input
    if ($ti.command) { $cmd = $ti.command }
    elseif ($ti.args) { $cmd = ($ti.args | ForEach-Object { $_ }) -join " " }
} catch {}
$block = $false
if ($cmd -match 'rm\\s+-[rf]+' -and $cmd -match '/') { $block = $true }
if ($cmd -match 'format\\s+[cC]:') { $block = $true }
if ($cmd -match 'del\\s+/[fs]*\\s*/[sq]*' -or $cmd -match 'rd\\s+/s\\s+/q') { $block = $true }
if ($block) {
    Write-Error "TappsMCP: Blocked potentially destructive command."
    exit 2
}
exit 0
""",
    "tapps-memory-capture.ps1": """\
# TappsMCP Stop hook - Memory Capture (Epic 34.5)
# Writes session quality data to .tapps-mcp/session-capture.json for
# persistence into shared memory on next session start.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $active = $data.stop_hook_active
} catch {
    $active = $false
}
if ($active -eq $true -or $active -eq "true" -or $active -eq "True") {
    exit 0
}
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$captureDir = "$projDir/.tapps-mcp"
$marker = "$captureDir/.validation-marker"
$validated = if (Test-Path $marker) { $true } else { $false }
$dateStr = (Get-Date -Format "yyyy-MM-dd")
try {
    $gitOutput = git diff --name-only HEAD 2>$null
    $filesEdited = @($gitOutput | Where-Object { $_ -match '\\.py$' }).Count
} catch {
    $filesEdited = 0
}
if (-not (Test-Path $captureDir)) {
    New-Item -ItemType Directory -Path $captureDir -Force | Out-Null
}
$capture = @{ date = $dateStr; validated = $validated; files_edited = $filesEdited }
$capture | ConvertTo-Json | Set-Content -Path "$captureDir/session-capture.json" -Encoding UTF8
exit 0
""",
}

CLAUDE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "SessionStart": [
        {
            "matcher": "startup|resume",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-session-start.ps1"
                    ),
                },
            ],
        },
        {
            "matcher": "compact",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-session-compact.ps1"
                    ),
                },
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "Edit|Write",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-post-edit.ps1"
                    ),
                },
            ],
        },
    ],
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-stop.ps1"
                    ),
                },
            ],
        },
    ],
    "TaskCompleted": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-task-completed.ps1"
                    ),
                },
            ],
        },
    ],
    "PreCompact": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-pre-compact.ps1"
                    ),
                },
            ],
        },
    ],
    "SubagentStart": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-subagent-start.ps1"
                    ),
                },
            ],
        },
    ],
    "SubagentStop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-subagent-stop.ps1"
                    ),
                },
            ],
        },
    ],
    "SessionEnd": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-session-end.ps1"
                    ),
                },
            ],
        },
    ],
    "PostToolUseFailure": [
        {
            "matcher": "mcp__tapps-mcp__.*",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-tool-failure.ps1"
                    ),
                },
            ],
        },
    ],
}

CLAUDE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "SessionStart": [
        {
            "matcher": "startup|resume",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-session-start.sh"},
            ],
        },
        {
            "matcher": "compact",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-session-compact.sh"},
            ],
        },
    ],
    "PostToolUse": [
        {
            "matcher": "Edit|Write",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-post-edit.sh"},
            ],
        },
    ],
    "Stop": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-stop.sh"},
            ],
        },
    ],
    "TaskCompleted": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-task-completed.sh"},
            ],
        },
    ],
    "PreCompact": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-pre-compact.sh"},
            ],
        },
    ],
    "SubagentStart": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-subagent-start.sh"},
            ],
        },
    ],
    "SubagentStop": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-subagent-stop.sh"},
            ],
        },
    ],
    "SessionEnd": [
        {
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-session-end.sh"},
            ],
        },
    ],
    "PostToolUseFailure": [
        {
            "matcher": "mcp__tapps-mcp__.*",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-tool-failure.sh"},
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Cursor hook script templates (Story 12.7)
# ---------------------------------------------------------------------------

CURSOR_HOOK_SCRIPTS: dict[str, str] = {
    "tapps-before-mcp.sh": """\
#!/usr/bin/env bash
# TappsMCP beforeMCPExecution hook
# Logs MCP tool invocations and reminds to call session_start.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin); print(d.get('tool','unknown'))"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
TOOL=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
case "$TOOL" in
  tapps_*)
    SENTINEL="${TMPDIR:-/tmp}/.tapps-session-started-$$"
    if [ "$TOOL" = "tapps_session_start" ]; then
      touch "$SENTINEL"
    elif [ ! -f "$SENTINEL" ]; then
      echo "REMINDER: Call tapps_session_start() first for best results."
    fi
    ;;
esac
echo "[TappsMCP] MCP tool invoked: $TOOL" >&2
exit 0
""",
    "tapps-after-edit.sh": """\
#!/usr/bin/env bash
# TappsMCP afterFileEdit hook (fire-and-forget)
# Reminds the agent to check quality after file edits.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin); print(d.get('file','unknown'))"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
FILE=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
echo "File edited: $FILE"
echo "Consider running tapps_quick_check to verify quality."
exit 0
""",
}

# ---------------------------------------------------------------------------
# Cursor hook script templates - PowerShell (Windows)
# ---------------------------------------------------------------------------

CURSOR_HOOK_SCRIPTS_PS: dict[str, str] = {
    "tapps-before-mcp.ps1": """\
# TappsMCP beforeMCPExecution hook
# Logs MCP tool invocations and reminds to call session_start.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $tool = if ($data.tool) { $data.tool } else { "unknown" }
} catch {
    $tool = "unknown"
}
if ($tool -match '^tapps_') {
    $sentinel = "$env:TEMP\\.tapps-session-started-$PID"
    if ($tool -eq 'tapps_session_start') {
        $null = New-Item -ItemType File -Path $sentinel -Force
    } elseif (-not (Test-Path $sentinel)) {
        Write-Output "REMINDER: Call tapps_session_start() first for best results."
    }
}
Write-Host "[TappsMCP] MCP tool invoked: $tool" -ForegroundColor Cyan
exit 0
""",
    "tapps-after-edit.ps1": """\
# TappsMCP afterFileEdit hook (fire-and-forget)
# Reminds the agent to check quality after file edits.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $file = if ($data.file) { $data.file }
            elseif ($data.tool_input.file_path) { $data.tool_input.file_path }
            elseif ($data.tool_input.path) { $data.tool_input.path }
            else { "unknown" }
} catch {
    $file = "unknown"
}
Write-Output "File edited: $file"
Write-Output "Consider running tapps_quick_check to verify quality."
exit 0
""",
}

PS1_PREFIX = "powershell -NoProfile -ExecutionPolicy Bypass -File "

CURSOR_HOOKS_CONFIG: dict[str, list[dict[str, str]]] = {
    "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
    "afterFileEdit": [{"command": ".cursor/hooks/tapps-after-edit.sh"}],
}

CURSOR_HOOKS_CONFIG_PS: dict[str, list[dict[str, str]]] = {
    "beforeMCPExecution": [
        {"command": PS1_PREFIX + ".cursor/hooks/tapps-before-mcp.ps1"},
    ],
    "afterFileEdit": [
        {"command": PS1_PREFIX + ".cursor/hooks/tapps-after-edit.ps1"},
    ],
}

# ---------------------------------------------------------------------------
# Memory capture hook config (Epic 34.5) — opt-in via memory_capture=True
# ---------------------------------------------------------------------------

MEMORY_CAPTURE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-capture.sh",
                },
            ],
        },
    ],
}

MEMORY_CAPTURE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-memory-capture.ps1"
                    ),
                },
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Destructive command guard (opt-in PreToolUse hook)
# ---------------------------------------------------------------------------

DESTRUCTIVE_GUARD_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-pre-bash.sh"},
            ],
        },
    ],
}

DESTRUCTIVE_GUARD_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-pre-bash.ps1"
                    ),
                },
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Engagement-level blocking hook variants (Epic 36.5)
# ---------------------------------------------------------------------------

CLAUDE_HOOK_SCRIPTS_BLOCKING: dict[str, str] = {
    "tapps-task-completed.sh": """\
#!/usr/bin/env bash
# TappsMCP TaskCompleted hook (HIGH engagement — BLOCKING)
# Blocks task completion if validation has not been run.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
MARKER="$PROJECT_DIR/.tapps-mcp/.validation-marker"
if [ -f "$MARKER" ]; then
  PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  AGE=$("$PYBIN" -c "
import time,sys
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
  exit 0
fi
echo "BLOCKED: tapps_validate_changed has not been run." >&2
echo "Run it before completing this task." >&2
exit 2
""",
    "tapps-stop.sh": """\
#!/usr/bin/env bash
# TappsMCP Stop hook (HIGH engagement — BLOCKING on first invocation)
# Blocks if no quality validation was run this session.
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
if [ -f "$MARKER" ]; then
  exit 0
fi
echo "BLOCKED: No quality validation was run this session." >&2
echo "Run tapps_validate_changed before ending." >&2
exit 2
""",
}

CLAUDE_HOOK_SCRIPTS_BLOCKING_PS: dict[str, str] = {
    "tapps-task-completed.ps1": """\
# TappsMCP TaskCompleted hook (HIGH engagement - BLOCKING)
# Blocks task completion if validation has not been run.
$null = $input | Out-Null
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$marker = "$projDir/.tapps-mcp/.validation-marker"
if (Test-Path $marker) {
    $content = Get-Content $marker -Raw
    try {
        $ts = [double]$content.Trim()
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        $age = $now - $ts
        if ($age -gt 3600) {
            $m = "BLOCKED: Validation stale (>1h). Run tapps_validate_changed."
            Write-Host $m -ForegroundColor Red
            exit 2
        }
    } catch {
        $m = "BLOCKED: Invalid marker. Run tapps_validate_changed."
        Write-Host $m -ForegroundColor Red
        exit 2
    }
    exit 0
}
Write-Host "BLOCKED: tapps_validate_changed has not been run." -ForegroundColor Red
Write-Host "Run it before completing this task." -ForegroundColor Red
exit 2
""",
    "tapps-stop.ps1": """\
# TappsMCP Stop hook (HIGH engagement - BLOCKING on first invocation)
# Blocks if no quality validation was run this session.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
$rawInput = @($input) -join "`n"
try {
    $data = $rawInput | ConvertFrom-Json
    $active = $data.stop_hook_active
} catch {
    $active = $false
}
if ($active -eq $true -or $active -eq "true" -or $active -eq "True") {
    exit 0
}
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$marker = "$projDir/.tapps-mcp/.validation-marker"
if (Test-Path $marker) {
    exit 0
}
Write-Host "BLOCKED: No quality validation was run this session." -ForegroundColor Red
Write-Host "Run tapps_validate_changed before ending." -ForegroundColor Red
exit 2
""",
}

# ---------------------------------------------------------------------------
# Prompt-type hook configuration (Epic 36.4) — opt-in
# ---------------------------------------------------------------------------

PROMPT_HOOK_CONFIG: dict[str, list[dict[str, Any]]] = {
    "PostToolUse": [
        {
            "matcher": "Edit|Write",
            "type": "prompt",
            "prompt": (
                "A file was just modified. Based on this tool output: "
                "$ARGUMENTS\n\nWas a Python file (.py) changed in a way "
                "that could affect code quality? If Python code was added, "
                "modified, or deleted, answer 'yes'. If only comments, "
                "whitespace, or non-Python files were changed, answer 'no'."
            ),
            "model": "haiku",
            "timeout": 15,
        },
    ],
}

# ---------------------------------------------------------------------------
# Engagement-level hook event sets (Epic 36.6)
# ---------------------------------------------------------------------------

# Events to include per engagement level (for generate_claude_hooks filtering)
ENGAGEMENT_HOOK_EVENTS: dict[str, set[str]] = {
    "high": {
        "SessionStart", "PostToolUse", "Stop", "TaskCompleted",
        "PreCompact", "SubagentStart", "SubagentStop", "SessionEnd",
        "PostToolUseFailure",
    },
    "medium": {
        "SessionStart", "PostToolUse", "Stop", "TaskCompleted",
        "PreCompact", "SubagentStart", "SubagentStop",
    },
    "low": {
        "SessionStart",
    },
}

# ---------------------------------------------------------------------------
# Agent Teams hook templates (Story 12.12)
# ---------------------------------------------------------------------------

AGENT_TEAMS_HOOK_SCRIPTS: dict[str, str] = {
    "tapps-teammate-idle.sh": """\
#!/usr/bin/env bash
# TappsMCP TeammateIdle hook
# Keeps quality watchdog active while gates are pending.
set -euo pipefail

INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin)"
PY="$PY; print(d.get('teammate_name',''))"
TEAMMATE=$(echo "$INPUT" | python3 -c "$PY" 2>/dev/null)

# Only keep the quality watchdog active
if [[ "$TEAMMATE" != "tapps-quality-watchdog" ]]; then
  exit 0
fi

echo "Quality watchdog — monitoring for issues" >&2
exit 2
""",
    "tapps-teams-task-completed.sh": """\
#!/usr/bin/env bash
# TappsMCP TaskCompleted hook (Agent Teams)
# Blocks task completion if quality gates fail.
set -euo pipefail

INPUT=$(cat)
MSG="Task blocked: run tapps_validate_changed"
MSG="$MSG to verify quality gates pass."
echo "$MSG" >&2
exit 2
""",
}

AGENT_TEAMS_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "TeammateIdle": [
        {
            "matcher": "tapps-quality-watchdog",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-teammate-idle.sh",
                },
            ],
        },
    ],
    "TaskCompleted": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (".claude/hooks/tapps-teams-task-completed.sh"),
                },
            ],
        },
    ],
}

AGENT_TEAMS_CLAUDE_MD_SECTION = """\

## Agent Teams (Optional)

If using Claude Code Agent Teams
(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`),
designate one teammate as a **quality watchdog**:

1. The quality watchdog runs `tapps_quick_check` on files changed
   by other teammates.
2. It messages other teammates via the shared mailbox when quality
   issues are found.
3. The `TaskCompleted` hook prevents any task from being marked
   complete until `tapps_validate_changed` passes.
4. The `TeammateIdle` hook keeps the watchdog active while quality
   issues remain unresolved.

To enable Agent Teams hooks, re-run `tapps_init` with
`agent_teams=True`.
"""
