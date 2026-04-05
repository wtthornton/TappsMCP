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
# Reads sidecar progress file for richer context when available.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active','false'))"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
ACTIVE=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null)
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
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
  [ -n "$REPORT_SUMMARY" ] && echo "$REPORT_SUMMARY"
fi
echo "Reminder: Run tapps_validate_changed before ending the session." >&2
exit 0
""",
    "tapps-task-completed.sh": """\
#!/usr/bin/env bash
# TappsMCP TaskCompleted hook
# Reminds to run quality checks but does NOT block.
# Reads sidecar progress file for richer context when available.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
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
  [ -n "$REPORT_SUMMARY" ] && echo "$REPORT_SUMMARY"
fi
MSG="Reminder: run tapps_validate_changed to confirm quality."
echo "$MSG" >&2
exit 0
""",
    "tapps-post-validate.sh": """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook (tapps_validate_changed)
# Reads the sidecar progress file and echoes a summary to the transcript.
# This provides a second delivery path for validation results.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.validation-progress.json"
if [ -f "$PROGRESS" ]; then
  PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  SUMMARY=$("$PYBIN" -c "
import json,sys
try:
    d=json.load(open('$PROGRESS'))
    status=d.get('status','unknown')
    if status=='completed':
        total=d.get('total',0)
        passed=sum(1 for r in d.get('results',[]) if r.get('gate_passed'))
        failed=total-passed
        ms=d.get('elapsed_ms',0)
        sec=ms/1000.0
        gp='ALL PASSED' if d.get('all_gates_passed') else f'{failed} FAILED'
        print(f'[TappsMCP] Validation: {total} files, {gp} ({sec:.1f}s)')
    elif status=='error':
        print(f'[TappsMCP] Validation error: {d.get(\"error\",\"unknown\")}')
    elif status=='running':
        done=d.get('completed',0)
        total=d.get('total',0)
        print(f'[TappsMCP] Validation in progress: {done}/{total} files')
except Exception:
    pass
" 2>/dev/null)
  if [ -n "$SUMMARY" ]; then
    echo "$SUMMARY"
  fi
fi
exit 0
""",
    "tapps-post-report.sh": """\
#!/usr/bin/env bash
# TappsMCP PostToolUse hook (tapps_report)
# Reads the report sidecar progress file and echoes a summary.
INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
PROGRESS="$PROJECT_DIR/.tapps-mcp/.report-progress.json"
if [ -f "$PROGRESS" ]; then
  PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
  SUMMARY=$("$PYBIN" -c "
import json,sys
try:
    d=json.load(open('$PROGRESS'))
    status=d.get('status','unknown')
    if status=='completed':
        total=d.get('total',0)
        results=d.get('results',[])
        if results:
            avg=sum(r.get('score',0) for r in results)/len(results)
            print(f'[TappsMCP] Report: {total} files scored, avg {avg:.1f}/100')
        else:
            print(f'[TappsMCP] Report: {total} files scored')
    elif status=='error':
        print(f'[TappsMCP] Report error: {d.get(\"error\",\"unknown\")}')
    elif status=='running':
        done=d.get('completed',0)
        total=d.get('total',0)
        print(f'[TappsMCP] Report in progress: {done}/{total} files')
except Exception:
    pass
" 2>/dev/null)
  [ -n "$SUMMARY" ] && echo "$SUMMARY"
fi
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
  *rm\\ -rf*|*rm\\ -fr*|*rm\\ -r\\ -f*|*rm\\ -rf\\ /*) BLOCK=1 ;;
  *format\\ c:*|*format\\ c:/*|*format\\ C:*|*format\\ C:/*) BLOCK=1 ;;
  *del\\ /f\\ /s\\ /q*|*del\\ /s\\ /q*|*rd\\ /s\\ /q*) BLOCK=1 ;;
  *:(){*:\\|:&*}\\;:*) BLOCK=1 ;;
esac
if [ "$BLOCK" = 1 ]; then
  echo "TappsMCP: Blocked potentially destructive command." >&2
  exit 2
fi
exit 0
""",
    "tapps-memory-auto-capture.sh": """\
#!/usr/bin/env bash
# TappsMCP Stop hook - Auto-Capture (Epic 65.5)
# Extracts durable facts from context and saves via tapps_memory save_bulk.
# Runs tapps-mcp auto-capture with stdin; configurable max_facts, min_context.
INPUT=$(cat)
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
ACTIVE=$(echo "$INPUT" | "$PYBIN" -c \
  "import sys,json; d=json.load(sys.stdin); print(d.get('stop_hook_active','false'))" \
  2>/dev/null)
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
if command -v tapps-mcp >/dev/null 2>&1; then
  echo "$INPUT" | tapps-mcp auto-capture --project-root "$PROJECT_DIR" 2>/dev/null || true
elif [ -n "$PYBIN" ]; then
  echo "$INPUT" | "$PYBIN" -m tapps_mcp.cli auto-capture --project-root "$PROJECT_DIR" 2>/dev/null || true
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
# Reads sidecar progress file for richer context when available.
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
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
            $failed = $total - $passed
            $gp = if ($d.all_gates_passed) { "all passed" } else { "$failed failed" }
            Write-Host "Last validation: $total files, $gp" -ForegroundColor Cyan
            exit 0
        }
    } catch {}
}
# Check report sidecar
$reportProgress = "$projDir/.tapps-mcp/.report-progress.json"
if (Test-Path $reportProgress) {
    try {
        $rd = Get-Content $reportProgress -Raw | ConvertFrom-Json
        if ($rd.status -eq "completed") {
            $results = @($rd.results)
            if ($results.Count -gt 0) {
                $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                Write-Output "Last report: $($results.Count) files, avg $avg/100"
            }
        }
    } catch {}
}
Write-Host "Reminder: Run tapps_validate_changed before ending the session." -ForegroundColor Yellow
exit 0
""",
    "tapps-task-completed.ps1": """\
# TappsMCP TaskCompleted hook
# Reminds to run quality checks but does NOT block.
# Reads sidecar progress file for richer context when available.
$null = $input | Out-Null
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
            $failed = $total - $passed
            $gp = if ($d.all_gates_passed) { "all passed" } else { "$failed failed" }
            Write-Host "Last validation: $total files, $gp" -ForegroundColor Cyan
            exit 0
        }
    } catch {}
}
# Check report sidecar
$reportProgress = "$projDir/.tapps-mcp/.report-progress.json"
if (Test-Path $reportProgress) {
    try {
        $rd = Get-Content $reportProgress -Raw | ConvertFrom-Json
        if ($rd.status -eq "completed") {
            $results = @($rd.results)
            if ($results.Count -gt 0) {
                $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                Write-Output "Last report: $($results.Count) files, avg $avg/100"
            }
        }
    } catch {}
}
Write-Host "Reminder: run tapps_validate_changed to confirm quality." -ForegroundColor Yellow
exit 0
""",
    "tapps-post-validate.ps1": """\
# TappsMCP PostToolUse hook (tapps_validate_changed)
# Reads the sidecar progress file and echoes a summary to the transcript.
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
            $failed = $total - $passed
            $sec = [math]::Round($d.elapsed_ms / 1000.0, 1)
            $gp = if ($d.all_gates_passed) { "ALL PASSED" } else { "$failed FAILED" }
            Write-Output "[TappsMCP] Validation: $total files, $gp ($($sec)s)"
        } elseif ($d.status -eq "error") {
            Write-Output "[TappsMCP] Validation error: $($d.error)"
        } elseif ($d.status -eq "running") {
            Write-Output "[TappsMCP] Validation in progress: $($d.completed)/$($d.total) files"
        }
    } catch {}
}
exit 0
""",
    "tapps-post-report.ps1": """\
# TappsMCP PostToolUse hook (tapps_report)
# Reads the report sidecar progress file and echoes a summary.
$rawInput = @($input) -join "`n"
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$progress = "$projDir/.tapps-mcp/.report-progress.json"
if (Test-Path $progress) {
    try {
        $d = Get-Content $progress -Raw | ConvertFrom-Json
        if ($d.status -eq "completed") {
            $total = $d.total
            $results = @($d.results)
            if ($results.Count -gt 0) {
                $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                Write-Output "[TappsMCP] Report: $total files scored, avg $avg/100"
            } else {
                Write-Output "[TappsMCP] Report: $total files scored"
            }
        } elseif ($d.status -eq "error") {
            Write-Output "[TappsMCP] Report error: $($d.error)"
        } elseif ($d.status -eq "running") {
            Write-Output "[TappsMCP] Report in progress: $($d.completed)/$($d.total) files"
        }
    } catch {}
}
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
    "tapps-memory-auto-capture.ps1": """\
# TappsMCP Stop hook - Auto-Capture (Epic 65.5)
# Extracts durable facts from context and saves via MemoryStore.
# Runs tapps-mcp auto-capture with stdin; configurable max_facts, min_context.
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
try {
    if (Get-Command tapps-mcp -ErrorAction SilentlyContinue) {
        $rawInput | tapps-mcp auto-capture --project-root $projDir 2>$null
    } else {
        $rawInput | python -m tapps_mcp.cli auto-capture --project-root $projDir 2>$null
    }
} catch {}
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
        {
            "matcher": "mcp__tapps-mcp__tapps_validate_changed",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-post-validate.ps1"
                    ),
                    "timeout": 10,
                },
            ],
        },
        {
            "matcher": "mcp__tapps-mcp__tapps_report",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-post-report.ps1"
                    ),
                    "timeout": 10,
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
        {
            "matcher": "mcp__tapps-mcp__tapps_validate_changed",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-post-validate.sh",
                    "timeout": 10,
                },
            ],
        },
        {
            "matcher": "mcp__tapps-mcp__tapps_report",
            "hooks": [
                {"type": "command", "command": ".claude/hooks/tapps-post-report.sh", "timeout": 10},
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

# Supported Cursor hooks.json event keys (schema: cursor-hooks/schema/hooks.schema.json).
# Only these keys are valid under "hooks"; invalid keys can cause the file to be ignored.
SUPPORTED_CURSOR_HOOK_KEYS: frozenset[str] = frozenset({
    "beforeShellExecution", "beforeMCPExecution", "afterFileEdit",
    "beforeReadFile", "beforeSubmitPrompt", "stop",
})

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
# Memory auto-capture hook config (Epic 65.5) — opt-in via memory_auto_capture=True
# ---------------------------------------------------------------------------

MEMORY_AUTO_CAPTURE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-auto-capture.sh",
                },
            ],
        },
    ],
}

MEMORY_AUTO_CAPTURE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-memory-auto-capture.ps1"
                    ),
                },
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# Memory capture hook config (Epic 34.5) — opt-in via memory_capture=True
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Memory auto-recall hook templates (Epic 65.4)
# Runs before agent prompt (PreCompact, SessionStart) to inject relevant memories.
# Calls tapps-mcp memory recall with query from prompt/last user message.
# Configurable: max_results (5), min_score (0.3), min_prompt_length (50).
# ---------------------------------------------------------------------------

def _memory_auto_recall_script(
    max_results: int = 5,
    min_score: float = 0.3,
    min_prompt_length: int = 50,
) -> str:
    """Return the bash script for memory auto-recall (Epic 65.4)."""
    return f'''#!/usr/bin/env bash
# TappsMCP Memory Auto-Recall (Epic 65.4)
# Injects relevant memories before agent prompt. Runs on PreCompact, SessionStart.
# Graceful fallback: no MemoryStore, MCP unavailable, empty results — exit 0.
INPUT=$(cat)
PY="import sys,json
try:
    d=json.load(sys.stdin)
    q=d.get('prompt','') or d.get('last_user_message','') or d.get('last_message','')
    if not q and 'messages' in d:
        ms=d.get('messages',[])
        if ms:
            last=ms[-1] if isinstance(ms[-1],dict) else {{}}
            q=last.get('content',last.get('text',''))
    if not q: q=d.get('context','') or 'project context architecture'
    q=(q or '')[:500]
    print(q)
except Exception:
    print('project context architecture')
"
PYBIN=$(command -v python3 2>/dev/null || command -v python 2>/dev/null)
QUERY=$(echo "$INPUT" | "$PYBIN" -c "$PY" 2>/dev/null || echo "project context architecture")
if [ ${{#QUERY}} -lt {min_prompt_length} ]; then
  exit 0
fi
PROJECT_DIR="${{CLAUDE_PROJECT_DIR:-.}}"
TAPPS=$(command -v tapps-mcp 2>/dev/null)
if [ -z "$TAPPS" ]; then
  exit 0
fi
OUT=$("$TAPPS" memory recall --query "$QUERY" --project-root "$PROJECT_DIR" \\
  --max-results {max_results} --min-score {min_score} 2>/dev/null)
if [ -n "$OUT" ]; then
  echo "$OUT"
fi
exit 0
'''


def _memory_auto_recall_script_ps(
    max_results: int = 5,
    min_score: float = 0.3,
    min_prompt_length: int = 50,
) -> str:
    """Return the PowerShell script for memory auto-recall (Epic 65.4)."""
    return f'''# TappsMCP Memory Auto-Recall (Epic 65.4)
# Injects relevant memories before agent prompt. Runs on PreCompact, SessionStart.
# Graceful fallback: no MemoryStore, MCP unavailable, empty results — exit 0.
$rawInput = @($input) -join "`n"
$query = "project context architecture"
try {{
    $data = $rawInput | ConvertFrom-Json
    $query = if ($data.prompt) {{ $data.prompt }}
             elseif ($data.last_user_message) {{ $data.last_user_message }}
             elseif ($data.last_message) {{ $data.last_message }}
             elseif ($data.context) {{ $data.context }}
             else {{ "project context architecture" }}
    if ($data.messages -and $data.messages.Count -gt 0) {{
        $last = $data.messages[-1]
        $c = if ($last.content) {{ $last.content }} elseif ($last.text) {{ $last.text }} else {{ "" }}
        if ($c) {{ $query = $c }}
    }}
    $query = ($query -as [string] -or "").Substring(0, [Math]::Min(500, ($query -as [string]).Length))
}} catch {{}}
if ($query.Length -lt {min_prompt_length}) {{
    exit 0
}}
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) {{ $projDir = "." }}
$tapps = Get-Command tapps-mcp -ErrorAction SilentlyContinue
if (-not $tapps) {{
    exit 0
}}
try {{
    $out = & tapps-mcp memory recall --query "$query" --project-root $projDir `
        --max-results {max_results} --min-score {min_score} 2>$null
    if ($out) {{ Write-Output $out }}
}} catch {{}}
exit 0
'''


MEMORY_AUTO_RECALL_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
    "SessionStart": [
        {
            "matcher": "startup|resume",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-auto-recall.sh",
                },
            ],
        },
        {
            "matcher": "compact",
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-auto-recall.sh",
                },
            ],
        },
    ],
    "PreCompact": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": ".claude/hooks/tapps-memory-auto-recall.sh",
                },
            ],
        },
    ],
}

MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
    "SessionStart": [
        {
            "matcher": "startup|resume",
            "hooks": [
                {
                    "type": "command",
                    "command": (
                        "powershell -NoProfile -ExecutionPolicy Bypass"
                        " -File .claude/hooks/tapps-memory-auto-recall.ps1"
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
                        " -File .claude/hooks/tapps-memory-auto-recall.ps1"
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
                        " -File .claude/hooks/tapps-memory-auto-recall.ps1"
                    ),
                },
            ],
        },
    ],
}

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
                print(f'  FAILED: {r[\"file\"]} ({r.get(\"score\",\"?\")}/100)')
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
""",
    "tapps-stop.sh": """\
#!/usr/bin/env bash
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
echo "Run tapps_validate_changed before ending." >&2
exit 2
""",
}

CLAUDE_HOOK_SCRIPTS_BLOCKING_PS: dict[str, str] = {
    "tapps-task-completed.ps1": """\
# TappsMCP TaskCompleted hook (HIGH engagement - BLOCKING)
# Blocks task completion if validation has not been run.
# Reads sidecar for richer context in systemMessage.
$null = $input | Out-Null
$projDir = $env:CLAUDE_PROJECT_DIR
if (-not $projDir) { $projDir = "." }
$marker = "$projDir/.tapps-mcp/.validation-marker"
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
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
    if (Test-Path $progress) {
        try {
            $d = Get-Content $progress -Raw | ConvertFrom-Json
            if ($d.status -eq "completed") {
                $total = $d.total
                $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
                $failed = $total - $passed
                $gp = if ($d.all_gates_passed) { "all passed" } else { "$failed failed" }
                Write-Output "Last validation: $total files, $gp"
                foreach ($r in $d.results) {
                    if (-not $r.gate_passed) {
                        Write-Output "  FAILED: $($r.file) ($($r.score)/100)"
                    }
                }
            }
        } catch {}
    }
    # Check report sidecar
    $reportProgress = "$projDir/.tapps-mcp/.report-progress.json"
    if (Test-Path $reportProgress) {
        try {
            $rd = Get-Content $reportProgress -Raw | ConvertFrom-Json
            if ($rd.status -eq "completed") {
                $results = @($rd.results)
                if ($results.Count -gt 0) {
                    $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                    Write-Output "Last report: $($results.Count) files, avg $avg/100"
                }
            }
        } catch {}
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
# Reads sidecar for richer context when validation was run.
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
$progress = "$projDir/.tapps-mcp/.validation-progress.json"
if (Test-Path $marker) {
    if (Test-Path $progress) {
        try {
            $d = Get-Content $progress -Raw | ConvertFrom-Json
            if ($d.status -eq "completed") {
                $total = $d.total
                $passed = @($d.results | Where-Object { $_.gate_passed -eq $true }).Count
                $failed = $total - $passed
                $gp = if ($d.all_gates_passed) { "all passed" } else { "$failed failed" }
                Write-Output "Last validation: $total files, $gp"
            }
        } catch {}
    }
    # Check report sidecar
    $reportProgress = "$projDir/.tapps-mcp/.report-progress.json"
    if (Test-Path $reportProgress) {
        try {
            $rd = Get-Content $reportProgress -Raw | ConvertFrom-Json
            if ($rd.status -eq "completed") {
                $results = @($rd.results)
                if ($results.Count -gt 0) {
                    $avg = [math]::Round(($results | Measure-Object -Property score -Average).Average, 1)
                    Write-Output "Last report: $($results.Count) files, avg $avg/100"
                }
            }
        } catch {}
    }
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
# Supported Claude Code lifecycle hooks (schema: claude-code-settings.json)
# ---------------------------------------------------------------------------
# Only these keys are valid under "hooks" in .claude/settings.json.
# PostCompact is NOT supported; invalid keys cause the entire settings file
# to be skipped by Claude Code. Used by init/upgrade to avoid writing or
# retaining unsupported keys.
SUPPORTED_CLAUDE_HOOK_KEYS: frozenset[str] = frozenset({
    "PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest",
    "Notification", "UserPromptSubmit", "Stop", "SubagentStart", "SubagentStop",
    "PreCompact", "TeammateIdle", "TaskCompleted", "Setup", "InstructionsLoaded",
    "ConfigChange", "WorktreeCreate", "WorktreeRemove", "SessionStart", "SessionEnd",
})

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
