"""Platform-specific generators for hooks, subagents, and skills.

Called from ``pipeline.init._setup_platform`` to create Claude Code and Cursor
configuration artifacts alongside the existing rule-file bootstrapping.
"""

from __future__ import annotations

import json
import stat
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Claude Code hook script templates (Story 12.5)
# ---------------------------------------------------------------------------

_CLAUDE_HOOK_SCRIPTS: dict[str, str] = {
    "tapps-session-start.sh": """\
#!/usr/bin/env bash
# TappsMCP SessionStart hook (startup/resume)
# Injects TappsMCP pipeline context into the session.
INPUT=$(cat)
echo "[TappsMCP] Session started — TappsMCP quality pipeline is active."
echo "Available tools: tapps_quick_check, tapps_score_file, tapps_quality_gate,"
echo "tapps_validate_changed, tapps_security_scan, tapps_consult_expert."
echo "Run tapps_session_start to initialize the session context."
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
PY="import sys,json; d=json.load(sys.stdin)"
PY="$PY; ti=d.get('tool_input',{})"
PY="$PY; print(ti.get('file_path',ti.get('path','')))"
FILE=$(echo "$INPUT" | python3 -c "$PY" 2>/dev/null)
if [ -n "$FILE" ] && echo "$FILE" | grep -qE '\\.py$'; then
  echo "Python file edited: $FILE"
  echo "Consider running tapps_quick_check on it."
fi
exit 0
""",
    "tapps-stop.sh": """\
#!/usr/bin/env bash
# TappsMCP Stop hook
# Blocks session stop until tapps_validate_changed has been called.
# IMPORTANT: Must check stop_hook_active to prevent infinite loops.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin)"
PY="$PY; print(d.get('stop_hook_active','false'))"
ACTIVE=$(echo "$INPUT" | python3 -c "$PY" 2>/dev/null)
if [ "$ACTIVE" = "True" ] || [ "$ACTIVE" = "true" ]; then
  exit 0
fi
echo "Run tapps_validate_changed before ending the session." >&2
exit 2
""",
    "tapps-task-completed.sh": """\
#!/usr/bin/env bash
# TappsMCP TaskCompleted hook
# Blocks task completion until quality gates pass.
INPUT=$(cat)
MSG="Before marking this task complete, run"
MSG="$MSG tapps_validate_changed to confirm quality."
echo "$MSG" >&2
exit 2
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
# Logs MCP tool invocations for observability.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin)"
PY="$PY; print(d.get('tool','unknown'))"
TOOL=$(echo "$INPUT" | python3 -c "$PY" 2>/dev/null)
echo "[TappsMCP] MCP tool invoked: $TOOL" >&2
exit 0
""",
    "tapps-after-edit.sh": """\
#!/usr/bin/env bash
# TappsMCP afterFileEdit hook (fire-and-forget)
# Reminds the agent to check quality after file edits.
INPUT=$(cat)
PY="import sys,json; d=json.load(sys.stdin)"
PY="$PY; print(d.get('file','unknown'))"
FILE=$(echo "$INPUT" | python3 -c "$PY" 2>/dev/null)
echo "File edited: $FILE"
echo "Consider running tapps_quick_check to verify quality."
exit 0
""",
    "tapps-stop.sh": """\
#!/usr/bin/env bash
# TappsMCP stop hook (Cursor)
# Uses followup_message to prompt validation before session ends.
# Note: Cursor does not support exit-2 blocking on the stop event.
INPUT=$(cat)
MSG="Before ending: please run tapps_validate_changed"
MSG="$MSG to confirm all changed files pass quality gates."
echo "{\"followup_message\": \"$MSG\"}"
exit 0
""",
}

_CURSOR_HOOKS_CONFIG: list[dict[str, str]] = [
    {
        "event": "beforeMCPExecution",
        "command": ".cursor/hooks/tapps-before-mcp.sh",
    },
    {
        "event": "afterFileEdit",
        "command": ".cursor/hooks/tapps-after-edit.sh",
    },
    {
        "event": "stop",
        "command": ".cursor/hooks/tapps-stop.sh",
    },
]

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
}


# ---------------------------------------------------------------------------
# Public generator functions
# ---------------------------------------------------------------------------


def generate_claude_hooks(project_root: Path) -> dict[str, Any]:
    """Generate Claude Code hook scripts and settings.json hooks config.

    Creates ``.claude/hooks/`` with 7 shell scripts and merges hook entries
    into ``.claude/settings.json``.

    Returns a summary dict with ``scripts_created`` and ``hooks_action``.
    """
    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    scripts_created: list[str] = []
    for name, content in _CLAUDE_HOOK_SCRIPTS.items():
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
    for event, entries in _CLAUDE_HOOKS_CONFIG.items():
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

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    action = "created" if hooks_added > 0 else "skipped"
    return {
        "scripts_created": scripts_created,
        "hooks_action": action,
        "hooks_added": hooks_added,
    }


def generate_cursor_hooks(project_root: Path) -> dict[str, Any]:
    """Generate Cursor hook scripts and ``.cursor/hooks.json`` config.

    Creates ``.cursor/hooks/`` with 3 shell scripts and merges hook entries
    into ``.cursor/hooks.json``.

    Returns a summary dict with ``scripts_created`` and ``hooks_action``.
    """
    hooks_dir = project_root / ".cursor" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    scripts_created: list[str] = []
    for name, content in _CURSOR_HOOK_SCRIPTS.items():
        script_path = hooks_dir / name
        if not script_path.exists():
            script_path.write_text(content, encoding="utf-8")
            script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
            scripts_created.append(name)

    # Merge hooks config into .cursor/hooks.json
    hooks_file = project_root / ".cursor" / "hooks.json"
    if hooks_file.exists():
        raw = hooks_file.read_text(encoding="utf-8")
        config: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    else:
        config = {}

    existing_hooks: list[dict[str, str]] = config.setdefault("hooks", [])
    existing_events = {e.get("event") for e in existing_hooks if isinstance(e, dict)}

    hooks_added = 0
    for entry in _CURSOR_HOOKS_CONFIG:
        if entry["event"] not in existing_events:
            existing_hooks.append(entry)
            hooks_added += 1

    hooks_file.parent.mkdir(parents=True, exist_ok=True)
    hooks_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    action = "created" if hooks_added > 0 else "skipped"
    return {
        "scripts_created": scripts_created,
        "hooks_action": action,
        "hooks_added": hooks_added,
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
