"""Platform-specific generators for hooks, subagents, and skills.

Called from ``pipeline.init._setup_platform`` to create Claude Code and Cursor
configuration artifacts alongside the existing rule-file bootstrapping.
"""

from __future__ import annotations

import json
import stat
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def _is_windows() -> bool:
    """Return True when running on Windows."""
    return sys.platform == "win32"


def _is_wrong_platform_command(command: str, *, win: bool) -> bool:
    """Return True if *command* references a tapps hook for the wrong platform.

    Only matches commands containing ``tapps-`` so that user-defined custom
    hooks are never touched.
    """
    if "tapps-" not in command:
        return False
    if win:
        # On Windows we expect .ps1 — flag .sh references
        return command.rstrip().endswith(".sh")
    # On Unix we expect .sh — flag powershell/.ps1 references
    return ".ps1" in command and "powershell" in command.lower()


def _migrate_claude_hook_commands(
    existing_hooks: dict[str, Any],
    correct_config: dict[str, list[dict[str, Any]]],
    *,
    win: bool,
) -> int:
    """Replace wrong-platform commands inside Claude Code hook entries.

    Claude hooks use nested structure:
    ``{"matcher": "...", "hooks": [{"type": "command", "command": "..."}]}``.

    Returns the number of commands migrated.
    """
    migrated = 0
    for event, matcher_entries in existing_hooks.items():
        if not isinstance(matcher_entries, list):
            continue
        for matcher_entry in matcher_entries:
            if not isinstance(matcher_entry, dict):
                continue
            inner_hooks = matcher_entry.get("hooks", [])
            if not isinstance(inner_hooks, list):
                continue
            for ih_idx, hook in enumerate(inner_hooks):
                if not isinstance(hook, dict):
                    continue
                cmd = hook.get("command", "")
                if not _is_wrong_platform_command(cmd, win=win):
                    continue
                # Find the replacement from correct_config by matcher
                matcher = matcher_entry.get("matcher")
                if event in correct_config:
                    for correct_entry in correct_config[event]:
                        if correct_entry.get("matcher") == matcher:
                            correct_inner = correct_entry.get("hooks", [])
                            if ih_idx < len(correct_inner):
                                inner_hooks[ih_idx] = correct_inner[ih_idx]
                                migrated += 1
                            break
    return migrated


# ---------------------------------------------------------------------------
# Claude Code hook script templates (Story 12.5)
# ---------------------------------------------------------------------------

_CLAUDE_HOOK_SCRIPTS: dict[str, str] = {
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
echo "Available MCP tools: tapps_quick_check, tapps_score_file, tapps_validate_changed."
exit 0
""",
}

# ---------------------------------------------------------------------------
# Claude Code hook script templates — PowerShell (Windows)
# ---------------------------------------------------------------------------

_CLAUDE_HOOK_SCRIPTS_PS: dict[str, str] = {
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
Write-Output "Available MCP tools: tapps_quick_check, tapps_score_file, tapps_validate_changed."
exit 0
""",
}

_CLAUDE_HOOKS_CONFIG_PS: dict[str, list[dict[str, Any]]] = {
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
}

_CLAUDE_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
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
}

# ---------------------------------------------------------------------------
# Cursor hook script templates (Story 12.7)
# ---------------------------------------------------------------------------

_CURSOR_HOOK_SCRIPTS: dict[str, str] = {
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
# Cursor hook script templates — PowerShell (Windows)
# ---------------------------------------------------------------------------

_CURSOR_HOOK_SCRIPTS_PS: dict[str, str] = {
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
    $sentinel = "$env:TEMP\.tapps-session-started-$PID"
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

_PS1_PREFIX = "powershell -NoProfile -ExecutionPolicy Bypass -File "

_CURSOR_HOOKS_CONFIG: dict[str, list[dict[str, str]]] = {
    "beforeMCPExecution": [{"command": ".cursor/hooks/tapps-before-mcp.sh"}],
    "afterFileEdit": [{"command": ".cursor/hooks/tapps-after-edit.sh"}],
}

_CURSOR_HOOKS_CONFIG_PS: dict[str, list[dict[str, str]]] = {
    "beforeMCPExecution": [
        {"command": _PS1_PREFIX + ".cursor/hooks/tapps-before-mcp.ps1"},
    ],
    "afterFileEdit": [
        {"command": _PS1_PREFIX + ".cursor/hooks/tapps-after-edit.ps1"},
    ],
}

# ---------------------------------------------------------------------------
# Subagent templates (Story 12.6)
# ---------------------------------------------------------------------------

_CLAUDE_AGENTS: dict[str, str] = {
    "tapps-reviewer.md": """\
---
name: tapps-reviewer
description: >-
  Use proactively to review code quality, run security scans, and enforce
  quality gates after editing Python files.
tools: Read, Glob, Grep
model: sonnet
permissionMode: dontAsk
memory: project
---

You are a TappsMCP quality reviewer. When invoked:

1. Identify which Python files were recently edited
2. Call `mcp__tapps-mcp__tapps_quick_check` on each changed file
3. If any file scores below 70, call `mcp__tapps-mcp__tapps_score_file` for a detailed breakdown
4. Summarize findings: file, score, top issues, suggested fixes
5. If overall quality is poor, recommend calling `mcp__tapps-mcp__tapps_quality_gate`

Focus on actionable feedback. Be concise.
""",
    "tapps-researcher.md": """\
---
name: tapps-researcher
description: >-
  Look up documentation, consult domain experts, and research best practices
  for the technologies used in this project.
tools: Read, Glob, Grep
model: haiku
memory: project
---

You are a TappsMCP research assistant. When invoked:

1. Call `mcp__tapps-mcp__tapps_research` to look up documentation
   for the relevant library or framework
2. If deeper expertise is needed, call
   `mcp__tapps-mcp__tapps_consult_expert` with the specific question
3. Summarize the findings with code examples and best practices
4. Reference the source documentation

Be thorough but concise. Cite specific sections from the documentation.
""",
    "tapps-validator.md": """\
---
name: tapps-validator
description: >-
  Run pre-completion validation on all changed files to confirm they meet
  quality thresholds before declaring work complete.
tools: Read, Glob, Grep
model: sonnet
permissionMode: dontAsk
memory: project
---

You are a TappsMCP validation agent. When invoked:

1. Call `mcp__tapps-mcp__tapps_validate_changed` to check all changed files
2. For each file that fails, report the file path, score, and top blocking issue
3. If all files pass, confirm explicitly that validation succeeded
4. If any files fail, list the minimum changes needed to pass the quality gate

Do not approve work that has not passed validation.
""",
    "tapps-review-fixer.md": """\
---
name: tapps-review-fixer
description: >-
  Combined review and fix agent. Scores a Python file, fixes issues found,
  and validates the result passes the quality gate. Use in worktrees for
  parallel multi-file review pipelines.
tools: Read, Glob, Grep, Write, Edit, Bash
model: sonnet
permissionMode: dontAsk
memory: project
---

You are a TappsMCP review-fixer agent. For each file assigned to you:

1. Call `mcp__tapps-mcp__tapps_score_file` to get the full 7-category breakdown
2. Call `mcp__tapps-mcp__tapps_security_scan` to check for security issues
3. Call `mcp__tapps-mcp__tapps_dead_code` to detect unused code
4. Fix all issues found: lint violations, security findings, dead code
5. Call `mcp__tapps-mcp__tapps_quality_gate` to verify the file passes
6. If the gate fails, fix remaining issues and re-run the gate
7. Report: file path, before/after scores, fixes applied, gate pass/fail

Be thorough but minimal - only change what is needed to pass the quality gate.
Do not refactor beyond what the issues require.
""",
}

_CURSOR_AGENTS: dict[str, str] = {
    "tapps-reviewer.md": """\
---
name: tapps-reviewer
description: >-
  Use proactively to review code quality, run security scans, and enforce
  quality gates after editing Python files.
model: sonnet
readonly: false
is_background: false
tools:
  - code_search
  - read_file
---

You are a TappsMCP quality reviewer. When invoked:

1. Identify which Python files were recently edited
2. Call the `tapps_quick_check` MCP tool on each changed file
3. If any file scores below 70, call `tapps_score_file` for a detailed breakdown
4. Summarize findings: file, score, top issues, suggested fixes
5. If overall quality is poor, recommend calling `tapps_quality_gate`

Focus on actionable feedback. Be concise.
""",
    "tapps-researcher.md": """\
---
name: tapps-researcher
description: >-
  Look up documentation, consult domain experts, and research best practices
  for the technologies used in this project.
model: haiku
readonly: true
is_background: false
tools:
  - code_search
  - read_file
---

You are a TappsMCP research assistant. When invoked:

1. Call the `tapps_research` MCP tool to look up documentation for the relevant library or framework
2. If deeper expertise is needed, call `tapps_consult_expert` with the specific question
3. Summarize the findings with code examples and best practices
4. Reference the source documentation

Be thorough but concise. Cite specific sections from the documentation.
""",
    "tapps-validator.md": """\
---
name: tapps-validator
description: >-
  Run pre-completion validation on all changed files to confirm they meet
  quality thresholds before declaring work complete.
model: sonnet
readonly: false
is_background: false
tools:
  - code_search
  - read_file
---

You are a TappsMCP validation agent. When invoked:

1. Call the `tapps_validate_changed` MCP tool to check all changed files
2. For each file that fails, report the file path, score, and top blocking issue
3. If all files pass, confirm explicitly that validation succeeded
4. If any files fail, list the minimum changes needed to pass the quality gate

Do not approve work that has not passed validation.
""",
    "tapps-review-fixer.md": """\
---
name: tapps-review-fixer
description: >-
  Combined review and fix agent. Scores a Python file, fixes issues found,
  and validates the result passes the quality gate. Use in worktrees for
  parallel multi-file review pipelines.
model: sonnet
readonly: false
is_background: false
tools:
  - code_search
  - read_file
  - edit_file
  - run_terminal_command
---

You are a TappsMCP review-fixer agent. For each file assigned to you:

1. Call `tapps_score_file` to get the full 7-category breakdown
2. Call `tapps_security_scan` to check for security issues
3. Call `tapps_dead_code` to detect unused code
4. Fix all issues found: lint violations, security findings, dead code
5. Call `tapps_quality_gate` to verify the file passes
6. If the gate fails, fix remaining issues and re-run the gate
7. Report: file path, before/after scores, fixes applied, gate pass/fail

Be thorough but minimal - only change what is needed to pass the quality gate.
Do not refactor beyond what the issues require.
""",
}

# ---------------------------------------------------------------------------
# Skills templates (Story 12.8)
# ---------------------------------------------------------------------------

_CLAUDE_SKILLS: dict[str, str] = {
    "tapps-score": """\
---
name: tapps-score
description: Score a Python file across 7 quality categories and display a structured report.
tools: mcp__tapps-mcp__tapps_score_file, mcp__tapps-mcp__tapps_quick_check
---

Score the specified Python file using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_quick_check` with the file path to get an instant score
2. If the score is below 80, call `mcp__tapps-mcp__tapps_score_file` for the full breakdown
3. Present the results in a table: category, score (0-100), top issue per category
4. Highlight any category scoring below 70 as a priority fix
5. Suggest the single highest-impact change the developer can make
""",
    "tapps-gate": """\
---
name: tapps-gate
description: Run a quality gate check and report pass/fail with blocking issues.
tools: mcp__tapps-mcp__tapps_quality_gate
---

Run a quality gate check using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_quality_gate` with the current project
2. Display the overall pass/fail result clearly
3. List each failing criterion with its actual vs. required value
4. If the gate fails, list the minimum changes required to pass
5. Do not declare work complete if the gate has not passed
""",
    "tapps-validate": """\
---
name: tapps-validate
description: Validate all changed files meet quality thresholds before declaring work complete.
tools: mcp__tapps-mcp__tapps_validate_changed
---

Validate all changed files using TappsMCP:

1. Call `mcp__tapps-mcp__tapps_validate_changed` to get the list of changed files and their scores
2. Display each file with its score and pass/fail status
3. If any file fails, list it with the top issue preventing it from passing
4. Confirm explicitly when all changed files pass before declaring work done
5. If any files fail, do NOT mark the task as complete
""",
    "tapps-review-pipeline": """\
---
name: tapps-review-pipeline
description: >-
  Orchestrate a parallel review-fix-validate pipeline across multiple changed files.
  Spawns tapps-review-fixer agents in worktrees for parallel processing.
tools: mcp__tapps-mcp__tapps_validate_changed, mcp__tapps-mcp__tapps_checklist
---

Run a parallel review-fix-validate pipeline on changed Python files:

1. Call `mcp__tapps-mcp__tapps_session_start` if not already called
2. Determine scope: detect changed Python files via git diff or accept a file list
3. For each file (or batch of files), spawn a `tapps-review-fixer` agent in a worktree:
   - Use the Task tool with `subagent_type: "general-purpose"` and `isolation: "worktree"`
   - Pass the file path and instructions to score, fix, and gate the file
4. Wait for all agents to complete and collect their results
5. Merge any worktree changes back (review diffs before accepting)
6. Call `mcp__tapps-mcp__tapps_validate_changed` to verify all files pass
7. Call `mcp__tapps-mcp__tapps_checklist(task_type="review")` for final verification
8. Present a summary table: file | before score | after score | gate | fixes applied
""",
}

_CURSOR_SKILLS: dict[str, str] = {
    "tapps-score": """\
---
name: tapps-score
description: Score a Python file across 7 quality categories and display a structured report.
mcp_tools:
  - tapps_score_file
  - tapps_quick_check
---

Score the specified Python file using TappsMCP:

1. Call `tapps_quick_check` with the file path to get an instant score
2. If the score is below 80, call `tapps_score_file` for the full 7-category breakdown
3. Present the results in a table: category, score (0-100), top issue per category
4. Highlight any category scoring below 70 as a priority fix
5. Suggest the single highest-impact change the developer can make
""",
    "tapps-gate": """\
---
name: tapps-gate
description: Run a quality gate check and report pass/fail with blocking issues.
mcp_tools:
  - tapps_quality_gate
---

Run a quality gate check using TappsMCP:

1. Call `tapps_quality_gate` with the current project
2. Display the overall pass/fail result clearly
3. List each failing criterion with its actual vs. required value
4. If the gate fails, list the minimum changes required to pass
5. Do not declare work complete if the gate has not passed
""",
    "tapps-validate": """\
---
name: tapps-validate
description: Validate all changed files meet quality thresholds before declaring work complete.
mcp_tools:
  - tapps_validate_changed
---

Validate all changed files using TappsMCP:

1. Call `tapps_validate_changed` to get the list of changed files and their scores
2. Display each file with its score and pass/fail status
3. If any file fails, list it with the top issue preventing it from passing
4. Confirm explicitly when all changed files pass before declaring work done
5. If any files fail, do NOT mark the task as complete
""",
    "tapps-review-pipeline": """\
---
name: tapps-review-pipeline
description: >-
  Orchestrate a parallel review-fix-validate pipeline across multiple changed files.
  Spawns tapps-review-fixer agents for parallel processing.
mcp_tools:
  - tapps_validate_changed
  - tapps_checklist
  - tapps_session_start
---

Run a parallel review-fix-validate pipeline on changed Python files:

1. Call `tapps_session_start` if not already called
2. Determine scope: detect changed Python files via git diff or accept a file list
3. For each file (or batch of files), spawn a `tapps-review-fixer` agent:
   - Pass the file path and instructions to score, fix, and gate the file
4. Wait for all agents to complete and collect their results
5. Review and merge any changes
6. Call `tapps_validate_changed` to verify all files pass
7. Call `tapps_checklist(task_type="review")` for final verification
8. Present a summary table: file | before score | after score | gate | fixes applied
""",
}


# ---------------------------------------------------------------------------
# Public generator functions
# ---------------------------------------------------------------------------


def generate_claude_hooks(
    project_root: Path,
    *,
    force_windows: bool | None = None,
) -> dict[str, Any]:
    """Generate Claude Code hook scripts and settings.json hooks config.

    Creates ``.claude/hooks/`` with 7 scripts (bash on Unix, PowerShell on
    Windows) and merges hook entries into ``.claude/settings.json``.

    Args:
        project_root: Target project root directory.
        force_windows: Override platform detection for testing.
            ``None`` (default) auto-detects via ``sys.platform``.

    Returns a summary dict with ``scripts_created`` and ``hooks_action``.
    """
    win = force_windows if force_windows is not None else _is_windows()
    script_templates = _CLAUDE_HOOK_SCRIPTS_PS if win else _CLAUDE_HOOK_SCRIPTS
    hooks_config = _CLAUDE_HOOKS_CONFIG_PS if win else _CLAUDE_HOOKS_CONFIG

    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Stop hook is always overwritten so upgrade gets the conditional-marker fix.
    scripts_always_overwrite = {"tapps-stop.ps1", "tapps-stop.sh"}
    scripts_created: list[str] = []
    for name, content in script_templates.items():
        script_path = hooks_dir / name
        if not script_path.exists() or name in scripts_always_overwrite:
            script_path.write_text(content, encoding="utf-8")
            if not win:
                script_path.chmod(
                    script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
                )
            scripts_created.append(name)

    # Clean up wrong-platform tapps scripts (e.g. .sh on Windows)
    wrong_ext = ".sh" if win else ".ps1"
    scripts_removed: list[str] = []
    for old_script in hooks_dir.glob(f"tapps-*{wrong_ext}"):
        old_script.unlink()
        scripts_removed.append(old_script.name)

    # Merge hooks config into .claude/settings.json
    settings_file = project_root / ".claude" / "settings.json"
    if settings_file.exists():
        raw = settings_file.read_text(encoding="utf-8")
        config: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    else:
        config = {}

    existing_hooks: dict[str, Any] = config.setdefault("hooks", {})
    hooks_added = 0
    for event, entries in hooks_config.items():
        if event not in existing_hooks:
            existing_hooks[event] = entries
            hooks_added += len(entries)
        else:
            # Merge: add entries whose matchers don't already exist
            existing_matchers = {
                e.get("matcher") for e in existing_hooks[event] if isinstance(e, dict)
            }
            for entry in entries:
                if entry.get("matcher") not in existing_matchers:
                    existing_hooks[event].append(entry)
                    hooks_added += 1

    # Replace wrong-platform commands in existing hook entries
    hooks_migrated = _migrate_claude_hook_commands(existing_hooks, hooks_config, win=win)

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    action = "migrated" if hooks_migrated > 0 else ("created" if hooks_added > 0 else "skipped")
    return {
        "scripts_created": scripts_created,
        "scripts_removed": scripts_removed,
        "hooks_action": action,
        "hooks_added": hooks_added,
        "hooks_migrated": hooks_migrated,
    }


def generate_cursor_hooks(
    project_root: Path,
    *,
    force_windows: bool | None = None,
) -> dict[str, Any]:
    """Generate Cursor hook scripts and ``.cursor/hooks.json`` config.

    Creates ``.cursor/hooks/`` with 3 scripts (bash on Unix, PowerShell on
    Windows) and merges hook entries into ``.cursor/hooks.json``.

    Args:
        project_root: Target project root directory.
        force_windows: Override platform detection for testing.
            ``None`` (default) auto-detects via ``sys.platform``.

    Returns a summary dict with ``scripts_created`` and ``hooks_action``.
    """
    win = force_windows if force_windows is not None else _is_windows()
    script_templates = _CURSOR_HOOK_SCRIPTS_PS if win else _CURSOR_HOOK_SCRIPTS
    hooks_config = _CURSOR_HOOKS_CONFIG_PS if win else _CURSOR_HOOKS_CONFIG

    hooks_dir = project_root / ".cursor" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    scripts_created: list[str] = []
    for name, content in script_templates.items():
        script_path = hooks_dir / name
        if not script_path.exists():
            script_path.write_text(content, encoding="utf-8")
            if not win:
                script_path.chmod(
                    script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
                )
            scripts_created.append(name)

    # Clean up wrong-platform tapps scripts (e.g. .sh on Windows)
    wrong_ext = ".sh" if win else ".ps1"
    scripts_removed: list[str] = []
    for old_script in hooks_dir.glob(f"tapps-*{wrong_ext}"):
        old_script.unlink()
        scripts_removed.append(old_script.name)

    # Remove deprecated stop hook scripts (validation is via tapps-mcp validate-changed)
    for name in ("tapps-stop.ps1", "tapps-stop.sh"):
        path = hooks_dir / name
        if path.exists():
            path.unlink()
            scripts_removed.append(name)

    # Merge hooks config into .cursor/hooks.json
    hooks_file = project_root / ".cursor" / "hooks.json"
    if hooks_file.exists():
        raw = hooks_file.read_text(encoding="utf-8")
        config: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    else:
        config = {}

    # Migrate old array format to new object format
    existing_hooks_raw = config.get("hooks", {})
    if isinstance(existing_hooks_raw, list):
        migrated: dict[str, list[dict[str, str]]] = {}
        for entry in existing_hooks_raw:
            if isinstance(entry, dict) and "event" in entry:
                event = entry["event"]
                cmd_obj = {k: v for k, v in entry.items() if k != "event"}
                migrated.setdefault(event, []).append(cmd_obj)
        existing_hooks_raw = migrated

    existing_hooks: dict[str, list[dict[str, str]]] = existing_hooks_raw

    # Remove stop hook; use CLI command tapps-mcp validate-changed instead.
    existing_hooks.pop("stop", None)

    hooks_added = 0
    for event, entries in hooks_config.items():
        if event not in existing_hooks:
            existing_hooks[event] = entries
            hooks_added += 1

    # Replace wrong-platform tapps commands in existing events
    hooks_migrated = 0
    for event, entries in existing_hooks.items():
        for i, entry in enumerate(entries):
            cmd = entry.get("command", "")
            if _is_wrong_platform_command(cmd, win=win):
                if event in hooks_config:
                    # Replace with the correct-platform entry
                    existing_hooks[event][i] = hooks_config[event][0]
                    hooks_migrated += 1

    config["version"] = 1
    config["hooks"] = existing_hooks
    hooks_file.parent.mkdir(parents=True, exist_ok=True)
    hooks_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    action = "migrated" if hooks_migrated > 0 else ("created" if hooks_added > 0 else "skipped")
    return {
        "scripts_created": scripts_created,
        "scripts_removed": scripts_removed,
        "hooks_action": action,
        "hooks_added": hooks_added,
        "hooks_migrated": hooks_migrated,
    }


def generate_subagent_definitions(project_root: Path, platform: str) -> dict[str, Any]:
    """Generate subagent definition files for the given platform.

    Creates 3 agent ``.md`` files in ``.claude/agents/`` or ``.cursor/agents/``
    depending on the platform. Existing files are skipped to preserve
    user customizations.

    Returns a summary dict with ``created`` and ``skipped`` lists.
    """
    if platform == "claude":
        agents_dir = project_root / ".claude" / "agents"
        templates = _CLAUDE_AGENTS
    elif platform == "cursor":
        agents_dir = project_root / ".cursor" / "agents"
        templates = _CURSOR_AGENTS
    else:
        return {"created": [], "skipped": [], "error": f"Unknown platform: {platform}"}

    agents_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    skipped: list[str] = []
    for name, content in templates.items():
        target = agents_dir / name
        if target.exists():
            skipped.append(name)
        else:
            target.write_text(content, encoding="utf-8")
            created.append(name)

    return {"created": created, "skipped": skipped}


def generate_skills(project_root: Path, platform: str) -> dict[str, Any]:
    """Generate SKILL.md files for the given platform.

    Creates 3 skill directories with ``SKILL.md`` in
    ``.claude/skills/`` or ``.cursor/skills/`` depending on the platform.
    Existing files are skipped to preserve user customizations.

    Returns a summary dict with ``created`` and ``skipped`` lists.
    """
    if platform == "claude":
        skills_base = project_root / ".claude" / "skills"
        templates = _CLAUDE_SKILLS
    elif platform == "cursor":
        skills_base = project_root / ".cursor" / "skills"
        templates = _CURSOR_SKILLS
    else:
        return {"created": [], "skipped": [], "error": f"Unknown platform: {platform}"}

    created: list[str] = []
    skipped: list[str] = []
    for skill_name, content in templates.items():
        skill_dir = skills_base / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        target = skill_dir / "SKILL.md"
        if target.exists():
            skipped.append(skill_name)
        else:
            target.write_text(content, encoding="utf-8")
            created.append(skill_name)

    return {"created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# Cursor rule types (Story 12.11)
# ---------------------------------------------------------------------------

_CURSOR_RULE_PIPELINE = """\
---
alwaysApply: true
---

# TAPPS Quality Pipeline

This project uses the TAPPS MCP server for code quality enforcement.

## Session Start (REQUIRED)

Call `tapps_session_start()` as the FIRST action in every session.

## After Editing Python Files (REQUIRED)

Call `tapps_quick_check(file_path)` after editing any Python file.

## Before Declaring Work Complete (BLOCKING)

Call `tapps_validate_changed()` to batch-validate all changed files.
The quality gate MUST pass before work is declared complete.
Call `tapps_checklist(task_type)` as the FINAL verification step.
"""

_CURSOR_RULE_PYTHON_QUALITY = """\
---
globs: "*.py"
alwaysApply: false
---

# Python Quality Standards

When Python files are referenced, enforce these quality standards:

## 7 Scoring Categories

TappsMCP scores Python code across 7 categories (0-100 each):

1. **Correctness** - Logic errors, type safety, edge cases
2. **Security** - Vulnerabilities, injection risks, secrets
3. **Maintainability** - Complexity, naming, structure
4. **Performance** - Efficiency, resource usage, scaling
5. **Documentation** - Docstrings, comments, clarity
6. **Testing** - Coverage, edge cases, assertions
7. **Style** - PEP 8, formatting, consistency

## Actions

- Call `tapps_quick_check(file_path)` on edited Python files
- Any category scoring below 70 needs immediate attention
- Call `tapps_score_file(file_path)` for full breakdown
"""

_CURSOR_RULE_EXPERT = """\
---
description: >-
  TappsMCP domain expert consultation — use when needing
  guidance on security, performance, architecture, testing,
  or other domain-specific best practices.
---

# Expert Consultation

Call `tapps_consult_expert(question)` for domain guidance.

## Available Expert Domains

- security, performance, architecture, testing
- documentation, accessibility, devops, database
- api, frontend, backend, data-science
- ml, cloud, mobile, embedded

## Usage

Provide a clear question and optionally specify the domain:

```
tapps_consult_expert(
    question="How should I handle auth tokens?",
    domain="security"
)
```

Returns RAG-backed expert guidance with confidence scores.
"""


def generate_cursor_rules(project_root: Path) -> dict[str, Any]:
    """Generate three Cursor rule files with different rule types.

    Creates ``.cursor/rules/`` with:
    - ``tapps-pipeline.mdc`` (alwaysApply)
    - ``tapps-python-quality.mdc`` (autoAttach via globs)
    - ``tapps-expert-consultation.mdc`` (agentRequested via description)

    Returns a summary dict with ``created`` and ``skipped`` lists.
    """
    rules_dir = project_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    rules: dict[str, str] = {
        "tapps-pipeline.mdc": _CURSOR_RULE_PIPELINE,
        "tapps-python-quality.mdc": _CURSOR_RULE_PYTHON_QUALITY,
        "tapps-expert-consultation.mdc": _CURSOR_RULE_EXPERT,
    }

    created: list[str] = []
    skipped: list[str] = []
    for name, content in rules.items():
        target = rules_dir / name
        if target.exists():
            skipped.append(name)
        else:
            target.write_text(content, encoding="utf-8")
            created.append(name)

    return {"created": created, "skipped": skipped}


# ---------------------------------------------------------------------------
# Agent Teams hooks (Story 12.12)
# ---------------------------------------------------------------------------

_AGENT_TEAMS_HOOK_SCRIPTS: dict[str, str] = {
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

_AGENT_TEAMS_HOOKS_CONFIG: dict[str, list[dict[str, Any]]] = {
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

_AGENT_TEAMS_CLAUDE_MD_SECTION = """\

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


def generate_agent_teams_hooks(
    project_root: Path,
) -> dict[str, Any]:
    """Generate Agent Teams hook scripts and merge config.

    Creates ``tapps-teammate-idle.sh`` and
    ``tapps-teams-task-completed.sh`` in ``.claude/hooks/`` and merges
    ``TeammateIdle`` and ``TaskCompleted`` entries into
    ``.claude/settings.json``.

    Returns a summary dict.
    """
    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    scripts_created: list[str] = []
    for name, content in _AGENT_TEAMS_HOOK_SCRIPTS.items():
        script_path = hooks_dir / name
        if not script_path.exists():
            script_path.write_text(content, encoding="utf-8")
            script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
            scripts_created.append(name)

    # Merge hooks config into .claude/settings.json
    settings_file = project_root / ".claude" / "settings.json"
    if settings_file.exists():
        raw = settings_file.read_text(encoding="utf-8")
        config: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    else:
        config = {}

    existing_hooks: dict[str, Any] = config.setdefault("hooks", {})
    hooks_added = 0
    for event, entries in _AGENT_TEAMS_HOOKS_CONFIG.items():
        if event not in existing_hooks:
            existing_hooks[event] = entries
            hooks_added += len(entries)

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    return {
        "scripts_created": scripts_created,
        "hooks_added": hooks_added,
    }


def get_agent_teams_claude_md_section() -> str:
    """Return the Agent Teams documentation section."""
    return _AGENT_TEAMS_CLAUDE_MD_SECTION


# ---------------------------------------------------------------------------
# Plugin bundle generators (Stories 12.9 + 12.10)
# ---------------------------------------------------------------------------

_CLAUDE_PLUGIN_README = """\
# TappsMCP — Claude Code Plugin

Code quality scoring, security scanning, and quality gates
for Python projects.

## Installation

Place this directory as a Claude Code plugin or install via:

```
claude plugin install tapps-mcp
```

## What's Included

- **MCP Server**: `tapps-mcp serve` with 12+ quality tools
- **Agents**: tapps-reviewer, tapps-researcher, tapps-validator
- **Skills**: `/tapps-score`, `/tapps-gate`, `/tapps-validate`
- **Hooks**: Session start, post-edit reminders, stop gate

## Usage

Once installed, the TappsMCP tools are available in every
session. Use `/tapps-score` to score a file, `/tapps-gate` to
run quality gates, and `/tapps-validate` before declaring
work complete.
"""

_CURSOR_PLUGIN_README = """\
# TappsMCP — Cursor Plugin

Code quality scoring, security scanning, and quality gates
for Python projects.

## Installation

Install via Cursor marketplace or place this directory as a
Cursor plugin.

## What's Included

- **MCP Server**: `tapps-mcp serve` with 12+ quality tools
- **Agents**: tapps-reviewer, tapps-researcher, tapps-validator
- **Skills**: `@tapps-score`, `@tapps-gate`, `@tapps-validate`
- **Hooks**: Before MCP, after edit reminders, stop prompt
- **Rules**: Pipeline (always), Python quality (auto-attach),
  Expert consultation (agent-requested)

## Usage

Once installed, the TappsMCP tools are available in every
session. Use `@tapps-score` to score a file, `@tapps-gate` to
run quality gates, and `@tapps-validate` before declaring
work complete.
"""


def generate_claude_plugin_bundle(
    output_dir: Path,
    version: str = "0.3.0",
) -> dict[str, Any]:
    """Generate a Claude Code plugin bundle directory.

    Creates the full plugin directory structure under *output_dir*
    including plugin.json, agents, skills, hooks, .mcp.json,
    and README.md.

    Returns a summary dict with ``files_created``.
    """
    files_created: list[str] = []

    # .claude-plugin/plugin.json
    meta_dir = output_dir / ".claude-plugin"
    meta_dir.mkdir(parents=True, exist_ok=True)
    plugin_data = {
        "name": "tapps-mcp",
        "version": version,
        "description": (
            "Code quality scoring, security scanning, and quality gates for Python projects"
        ),
    }
    (meta_dir / "plugin.json").write_text(
        json.dumps(plugin_data, indent=2) + "\n", encoding="utf-8"
    )
    files_created.append(".claude-plugin/plugin.json")

    # agents/
    agents_dir = output_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name, content in _CLAUDE_AGENTS.items():
        (agents_dir / name).write_text(content, encoding="utf-8")
        files_created.append(f"agents/{name}")

    # skills/
    for skill_name, content in _CLAUDE_SKILLS.items():
        skill_dir = output_dir / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        files_created.append(f"skills/{skill_name}/SKILL.md")

    # hooks/
    hooks_dir = output_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hooks_json_data: dict[str, Any] = {}
    for event, entries in _CLAUDE_HOOKS_CONFIG.items():
        plugin_entries = []
        for entry in entries:
            pe: dict[str, Any] = {}
            if "matcher" in entry:
                pe["matcher"] = entry["matcher"]
            pe["hooks"] = [
                {
                    "type": h["type"],
                    "command": h["command"].replace(".claude/hooks/", "hooks/"),
                }
                for h in entry["hooks"]
            ]
            plugin_entries.append(pe)
        hooks_json_data[event] = plugin_entries
    (hooks_dir / "hooks.json").write_text(
        json.dumps({"hooks": hooks_json_data}, indent=2) + "\n",
        encoding="utf-8",
    )
    files_created.append("hooks/hooks.json")

    for name, content in _CLAUDE_HOOK_SCRIPTS.items():
        script_path = hooks_dir / name
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        files_created.append(f"hooks/{name}")

    # .mcp.json — Claude Code uses "." (CWD == project root, no ${workspaceFolder})
    mcp_config = {
        "mcpServers": {
            "tapps-mcp": {
                "command": "uvx",
                "args": ["tapps-mcp", "serve"],
                "env": {
                    "TAPPS_MCP_PROJECT_ROOT": ".",
                },
            },
        },
    }
    (output_dir / ".mcp.json").write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")
    files_created.append(".mcp.json")

    # README.md
    (output_dir / "README.md").write_text(_CLAUDE_PLUGIN_README, encoding="utf-8")
    files_created.append("README.md")

    return {"files_created": files_created}


def generate_cursor_plugin_bundle(
    output_dir: Path,
    version: str = "0.3.0",
) -> dict[str, Any]:
    """Generate a Cursor plugin bundle directory.

    Creates the full plugin directory structure under *output_dir*
    including plugin.json, agents, skills, hooks, rules, mcp.json,
    logo.png placeholder, and README.md.

    Returns a summary dict with ``files_created``.
    """
    import base64

    files_created: list[str] = []

    # .cursor-plugin/plugin.json
    meta_dir = output_dir / ".cursor-plugin"
    meta_dir.mkdir(parents=True, exist_ok=True)
    plugin_data = {
        "name": "tapps-mcp-plugin",
        "displayName": "TappsMCP Quality Tools",
        "author": "TappsMCP Team",
        "description": (
            "Code quality scoring, security scanning, and quality gates for Python projects"
        ),
        "keywords": [
            "code-quality",
            "security",
            "scoring",
            "mcp",
            "python",
        ],
        "license": "MIT",
        "version": version,
    }
    (meta_dir / "plugin.json").write_text(
        json.dumps(plugin_data, indent=2) + "\n", encoding="utf-8"
    )
    files_created.append(".cursor-plugin/plugin.json")

    # agents/
    agents_dir = output_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name, content in _CURSOR_AGENTS.items():
        (agents_dir / name).write_text(content, encoding="utf-8")
        files_created.append(f"agents/{name}")

    # skills/
    for skill_name, content in _CURSOR_SKILLS.items():
        skill_dir = output_dir / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        files_created.append(f"skills/{skill_name}/SKILL.md")

    # hooks/
    hooks_dir = output_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    cursor_hooks_obj: dict[str, list[dict[str, str]]] = {
        event: [
            {"command": cmd["command"].replace(".cursor/hooks/", "hooks/")}
            for cmd in cmds
        ]
        for event, cmds in _CURSOR_HOOKS_CONFIG.items()
    }
    (hooks_dir / "hooks.json").write_text(
        json.dumps({"version": 1, "hooks": cursor_hooks_obj}, indent=2) + "\n",
        encoding="utf-8",
    )
    files_created.append("hooks/hooks.json")

    for name, content in _CURSOR_HOOK_SCRIPTS.items():
        script_path = hooks_dir / name
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        files_created.append(f"hooks/{name}")

    # rules/
    rules_dir = output_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules = {
        "tapps-pipeline.mdc": _CURSOR_RULE_PIPELINE,
        "tapps-python-quality.mdc": _CURSOR_RULE_PYTHON_QUALITY,
        "tapps-expert-consultation.mdc": _CURSOR_RULE_EXPERT,
    }
    for name, content in rules.items():
        (rules_dir / name).write_text(content, encoding="utf-8")
        files_created.append(f"rules/{name}")

    # mcp.json
    mcp_config = {
        "mcpServers": {
            "tapps-mcp": {
                "command": "uvx",
                "args": ["tapps-mcp", "serve"],
                "env": {
                    "TAPPS_MCP_PROJECT_ROOT": ("${workspaceFolder}"),
                },
            },
        },
    }
    (output_dir / "mcp.json").write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")
    files_created.append("mcp.json")

    # logo.png placeholder (1x1 transparent PNG)
    _png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5E"
        "rkJggg=="
    )
    (output_dir / "logo.png").write_bytes(base64.b64decode(_png))
    files_created.append("logo.png")

    # README.md
    (output_dir / "README.md").write_text(_CURSOR_PLUGIN_README, encoding="utf-8")
    files_created.append("README.md")

    # LICENSE
    license_text = "MIT License\n\nCopyright (c) TappsMCP Team\n"
    (output_dir / "LICENSE").write_text(license_text, encoding="utf-8")
    files_created.append("LICENSE")

    return {"files_created": files_created}


# ---------------------------------------------------------------------------
# VS Code / Copilot Instructions (Story 12.13)
# ---------------------------------------------------------------------------

_COPILOT_INSTRUCTIONS = """\
# TappsMCP Quality Tools

This project uses TappsMCP for code quality analysis. When TappsMCP is
available as an MCP server (configured in `.vscode/mcp.json`), use the
following tools to maintain code quality throughout development.

## Key Tools

- `tapps_session_start` — Initialize a TappsMCP session at the start of
  each work session. Call this first.
- `tapps_quick_check` — Run a quick quality check on a single file after
  editing. Returns score and top issues.
- `tapps_quality_gate` — Run a pass/fail quality gate against a configurable
  preset (development, staging, or production).
- `tapps_validate_changed` — Validate all changed files against the quality
  gate. Call this before declaring work complete.
- `tapps_consult_expert` — Consult a domain expert (security, performance,
  architecture, testing, and more) for guidance.
- `tapps_score_file` — Get a detailed 7-category quality score for any file.

## Workflow

1. Start a session: call `tapps_session_start`
2. After editing Python files: call `tapps_quick_check` on changed files
3. Before creating a PR or declaring work complete: call
   `tapps_validate_changed`
4. For domain-specific guidance: call `tapps_consult_expert` with the
   relevant domain

## Quality Scoring Categories

TappsMCP scores code across 7 categories (0-100 each):
correctness, security, maintainability, performance, documentation,
testing, and style.
"""


def generate_copilot_instructions(project_root: Path) -> dict[str, Any]:
    """Generate ``.github/copilot-instructions.md`` for VS Code Copilot.

    Creates the ``.github/`` directory if it does not exist and writes
    the instructions file. Idempotent — re-running overwrites with the
    same content.

    Returns a summary dict with ``file`` and ``action``.
    """
    github_dir = project_root / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    target = github_dir / "copilot-instructions.md"
    target.write_text(_COPILOT_INSTRUCTIONS, encoding="utf-8")
    return {"file": str(target), "action": "created"}


# ---------------------------------------------------------------------------
# Cursor BugBot rules (Story 12.14)
# ---------------------------------------------------------------------------

_BUGBOT_RULES = """\
# TappsMCP Quality Standards for BugBot

This project uses TappsMCP (Code Quality MCP Server) for automated quality
analysis. The following standards are enforced during PR review.

## Code Quality Standards

All Python files must meet TappsMCP scoring thresholds:
- Overall score: >= 70 (development), >= 80 (staging), >= 90 (production)
- No individual category score below 50

### Scoring Categories

| Category | What BugBot Should Check |
|----------|-------------------------|
| Correctness | Logic errors, unchecked return values, unreachable code |
| Security | Hardcoded secrets, unsafe deserialization, injection vulns |
| Maintainability | Functions > 50 lines, cyclomatic complexity > 10 |
| Performance | Nested loops on large data, sync I/O in async context |
| Documentation | Missing docstrings on public API, outdated params |
| Testing | Functions without test coverage, real external service calls |
| Style | Inconsistent naming, bare `except`, missing type annotations |

## Security Requirements

Flag any of the following as blocking issues:
- Hardcoded passwords, API keys, tokens, or secrets
- Use of `eval()` or `exec()` with non-literal arguments
- `pickle.loads()` on data from external sources
- Raw SQL string concatenation (use parameterized queries)
- File path operations without validation against allowed base dir
- `subprocess` calls with `shell=True` and interpolated user input

## Python Style Rules

Flag the following as non-blocking warnings:
- Public functions and methods without type annotations
- Public classes and functions without docstrings
- Bare `except:` clauses (must specify exception type)
- Functions with cyclomatic complexity > 10
- Functions longer than 50 lines (excluding docstrings/blanks)
- Mutable default arguments in function signatures

## Testing Requirements

Flag the following as non-blocking warnings:
- New public functions without a corresponding test in `tests/`
- Tests that make real HTTP requests without mocking
- Tests that read from or write to production configuration files
- Tests that depend on environment variables without explicit fixtures

## Directory Hierarchy

This `BUGBOT.md` applies to all files in `.cursor/` and subdirectories.
Place a subdirectory `BUGBOT.md` to override these rules for specific
sub-packages with different thresholds.
"""


def generate_bugbot_rules(project_root: Path) -> dict[str, Any]:
    """Generate ``.cursor/BUGBOT.md`` for Cursor BugBot PR reviews.

    Creates the ``.cursor/`` directory if needed and writes the rules
    file. Idempotent — re-running overwrites with the same content.

    Returns a summary dict with ``file`` and ``action``.
    """
    cursor_dir = project_root / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    target = cursor_dir / "BUGBOT.md"
    target.write_text(_BUGBOT_RULES, encoding="utf-8")
    return {"file": str(target), "action": "created"}


# ---------------------------------------------------------------------------
# CI / Headless workflow (Story 12.16)
# ---------------------------------------------------------------------------

_CI_WORKFLOW = """\
# .github/workflows/tapps-quality.yml
# Generated by TappsMCP tapps_init — edit as needed
name: TappsMCP Quality Gate

on:
  pull_request:
    paths:
      - "**.py"

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install TappsMCP
        run: pip install tapps-mcp

      - name: Run TappsMCP quality gate
        env:
          TAPPS_MCP_PROJECT_ROOT: ${{ github.workspace }}
        run: |
          tapps-mcp validate-changed \\
            --preset staging
"""

_CI_CLAUDE_MD_SECTION = """\

## CI Integration

TappsMCP can run in CI without an interactive session:

### Direct Python invocation (recommended for CI)

```bash
# Install TappsMCP
pip install tapps-mcp

# Validate changed files
TAPPS_MCP_PROJECT_ROOT=/workspace \\
  tapps-mcp validate-changed --preset staging
```

### Claude Code headless mode

```bash
claude --headless \\
  --allowedTools "mcp__tapps-mcp__tapps_validate_changed" \\
  "Run tapps_validate_changed with preset=staging"
```

### VS Code / headless — enableAllProjectMcpServers

In headless or non-interactive VS Code contexts, set:
`claude.enableAllProjectMcpServers: true` in workspace settings.

### Setup hook for CI onboarding

```bash
claude --init-only \\
  --allowedTools "mcp__tapps-mcp__*" \\
  --project-root /workspace
```
"""


def generate_ci_workflow(project_root: Path) -> dict[str, Any]:
    """Generate ``.github/workflows/tapps-quality.yml`` GitHub Actions workflow.

    Creates the ``.github/workflows/`` directory if needed and writes the
    workflow file. Idempotent — re-running overwrites with same content.

    Returns a summary dict with ``file`` and ``action``.
    """
    wf_dir = project_root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    target = wf_dir / "tapps-quality.yml"
    target.write_text(_CI_WORKFLOW, encoding="utf-8")
    return {"file": str(target), "action": "created"}


def get_ci_claude_md_section() -> str:
    """Return the CI Integration documentation section for CLAUDE.md."""
    return _CI_CLAUDE_MD_SECTION
