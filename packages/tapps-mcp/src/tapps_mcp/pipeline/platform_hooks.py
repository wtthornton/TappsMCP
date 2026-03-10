"""Hook generation logic for Claude Code and Cursor.

Creates hook script files and merges hook configuration into platform
settings files. Extracted from ``platform_generators.py`` to reduce file size.
"""

from __future__ import annotations

import json
import stat
import sys
from typing import TYPE_CHECKING, Any

from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS as _CLAUDE_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS_BLOCKING as _CLAUDE_HOOK_SCRIPTS_BLOCKING,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS_BLOCKING_PS as _CLAUDE_HOOK_SCRIPTS_BLOCKING_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS_PS as _CLAUDE_HOOK_SCRIPTS_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOKS_CONFIG as _CLAUDE_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOKS_CONFIG_PS as _CLAUDE_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_HOOK_SCRIPTS as _CURSOR_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_HOOK_SCRIPTS_PS as _CURSOR_HOOK_SCRIPTS_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_HOOKS_CONFIG as _CURSOR_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_HOOKS_CONFIG_PS as _CURSOR_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    DESTRUCTIVE_GUARD_HOOKS_CONFIG as _DESTRUCTIVE_GUARD_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    DESTRUCTIVE_GUARD_HOOKS_CONFIG_PS as _DESTRUCTIVE_GUARD_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    ENGAGEMENT_HOOK_EVENTS as _ENGAGEMENT_HOOK_EVENTS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    MEMORY_AUTO_CAPTURE_HOOKS_CONFIG as _MEMORY_AUTO_CAPTURE_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    MEMORY_AUTO_CAPTURE_HOOKS_CONFIG_PS as _MEMORY_AUTO_CAPTURE_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    MEMORY_AUTO_RECALL_HOOKS_CONFIG as _MEMORY_AUTO_RECALL_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS as _MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    MEMORY_CAPTURE_HOOKS_CONFIG as _MEMORY_CAPTURE_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    MEMORY_CAPTURE_HOOKS_CONFIG_PS as _MEMORY_CAPTURE_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    PROMPT_HOOK_CONFIG as _PROMPT_HOOK_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    _memory_auto_recall_script as _memory_auto_recall_script_fn,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    _memory_auto_recall_script_ps as _memory_auto_recall_script_ps_fn,
)

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
        # On Windows we expect .ps1 -- flag .sh references
        return command.rstrip().endswith(".sh")
    # On Unix we expect .sh -- flag powershell/.ps1 references
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
# Engagement level: transform hook script wording (Epic 18.7)
# ---------------------------------------------------------------------------


def _hook_content_for_engagement(content: str, engagement_level: str) -> str:
    """Adjust hook script echo/reminder text by engagement level."""
    if engagement_level == "high":
        content = content.replace("Consider running", "MUST run")
        content = content.replace("Reminder:", "REQUIRED:")
        content = content.replace("Reminder ", "REQUIRED: ")
    elif engagement_level == "low":
        content = content.replace("REQUIRED:", "Consider:")
        content = content.replace("MUST run", "Consider running")
        content = content.replace("You MUST run", "Consider running")
    return content


# ---------------------------------------------------------------------------
# Public generator functions: hooks
# ---------------------------------------------------------------------------


def _filter_hooks_config(
    hooks_config: dict[str, list[dict[str, Any]]],
    allowed_events: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Filter hooks config to only include allowed events."""
    return {event: entries for event, entries in hooks_config.items() if event in allowed_events}


def _filter_scripts(
    script_templates: dict[str, str],
    allowed_events: set[str],
) -> dict[str, str]:
    """Filter script templates by engagement-level event set.

    Maps script filenames to their corresponding hook events and only
    includes scripts whose event is in the allowed set.
    """
    # Map script name prefixes to their hook events
    script_event_map: dict[str, str] = {
        "tapps-session-start": "SessionStart",
        "tapps-session-compact": "SessionStart",
        "tapps-post-edit": "PostToolUse",
        "tapps-stop": "Stop",
        "tapps-task-completed": "TaskCompleted",
        "tapps-pre-compact": "PreCompact",
        "tapps-subagent-start": "SubagentStart",
        "tapps-subagent-stop": "SubagentStop",
        "tapps-session-end": "SessionEnd",
        "tapps-tool-failure": "PostToolUseFailure",
        "tapps-memory-capture": "Stop",
        "tapps-memory-auto-capture": "Stop",
        "tapps-pre-bash": "PreToolUse",
    }

    filtered: dict[str, str] = {}
    for name, content in script_templates.items():
        # Extract base name without extension
        base = name.rsplit(".", 1)[0]
        event = script_event_map.get(base, "")
        if event in allowed_events:
            filtered[name] = content
    return filtered


def generate_claude_hooks(
    project_root: Path,
    *,
    force_windows: bool | None = None,
    engagement_level: str = "medium",
    prompt_hooks: bool = False,
    destructive_guard: bool = False,
) -> dict[str, Any]:
    """Generate Claude Code hook scripts and settings.json hooks config.

    Creates ``.claude/hooks/`` with hook scripts (bash on Unix, PowerShell on
    Windows) and merges hook entries into ``.claude/settings.json``.

    The number of hooks varies by engagement level:
    - **high**: 10 events, blocking on Stop/TaskCompleted, all advisory hooks
    - **medium**: 7 events, all advisory (current default behavior)
    - **low**: 1 event (SessionStart only — minimal footprint)

    Args:
        project_root: Target project root directory.
        force_windows: Override platform detection for testing.
            ``None`` (default) auto-detects via ``sys.platform``.
        engagement_level: high (blocking), medium (advisory), low (minimal).
        prompt_hooks: When True, add a prompt-type PostToolUse hook using
            Haiku for intelligent file change detection (~$0.001/eval).
        destructive_guard: When True, add a PreToolUse hook that blocks Bash
            commands containing destructive patterns (rm -rf, format c:, etc.).

    Returns a summary dict with ``scripts_created`` and ``hooks_action``.
    """
    win = force_windows if force_windows is not None else _is_windows()
    allowed_events = set(
        _ENGAGEMENT_HOOK_EVENTS.get(
            engagement_level,
            _ENGAGEMENT_HOOK_EVENTS["medium"],
        ),
    )
    if destructive_guard:
        allowed_events.add("PreToolUse")

    # Select base scripts and config
    base_scripts = _CLAUDE_HOOK_SCRIPTS_PS if win else _CLAUDE_HOOK_SCRIPTS
    hooks_config = dict(_CLAUDE_HOOKS_CONFIG_PS if win else _CLAUDE_HOOKS_CONFIG)
    if destructive_guard:
        dg_config = _DESTRUCTIVE_GUARD_HOOKS_CONFIG_PS if win else _DESTRUCTIVE_GUARD_HOOKS_CONFIG
        for event, entries in dg_config.items():
            hooks_config.setdefault(event, []).extend(entries)

    # At high engagement, overlay blocking variants for Stop/TaskCompleted
    script_templates = dict(base_scripts)
    if engagement_level == "high":
        blocking = _CLAUDE_HOOK_SCRIPTS_BLOCKING_PS if win else _CLAUDE_HOOK_SCRIPTS_BLOCKING
        script_templates.update(blocking)

    # Filter to only the events allowed at this engagement level
    script_templates = _filter_scripts(script_templates, allowed_events)
    hooks_config = _filter_hooks_config(hooks_config, allowed_events)

    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Stop and task-completed hooks always overwrite (engagement change).
    scripts_always_overwrite = {
        "tapps-stop.ps1",
        "tapps-stop.sh",
        "tapps-task-completed.ps1",
        "tapps-task-completed.sh",
    }
    scripts_created: list[str] = []
    for name, content in script_templates.items():
        script_path = hooks_dir / name
        if not script_path.exists() or name in scripts_always_overwrite:
            text = _hook_content_for_engagement(content, engagement_level)
            script_path.write_text(text, encoding="utf-8")
            if not win:
                script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
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
            # Copy to avoid mutating the module-level template lists
            existing_hooks[event] = list(entries)
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

    # Add prompt-type hook if opted-in
    if prompt_hooks and "PostToolUse" in allowed_events:
        prompt_entries = _PROMPT_HOOK_CONFIG.get("PostToolUse", [])
        if "PostToolUse" not in existing_hooks:
            existing_hooks["PostToolUse"] = list(prompt_entries)
        else:
            # Check if prompt hook already exists
            has_prompt = any(
                e.get("type") == "prompt"
                for e in existing_hooks["PostToolUse"]
                if isinstance(e, dict)
            )
            if not has_prompt:
                existing_hooks["PostToolUse"].extend(prompt_entries)
                hooks_added += len(prompt_entries)

    # Replace wrong-platform commands in existing hook entries
    hooks_migrated = _migrate_claude_hook_commands(
        existing_hooks,
        hooks_config,
        win=win,
    )

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )

    action = "migrated" if hooks_migrated > 0 else ("created" if hooks_added > 0 else "skipped")
    return {
        "scripts_created": scripts_created,
        "scripts_removed": scripts_removed,
        "hooks_action": action,
        "hooks_added": hooks_added,
        "hooks_migrated": hooks_migrated,
        "engagement_level": engagement_level,
        "prompt_hooks": prompt_hooks,
        "destructive_guard": destructive_guard,
    }


def generate_cursor_hooks(
    project_root: Path,
    *,
    force_windows: bool | None = None,
    engagement_level: str = "medium",
) -> dict[str, Any]:
    """Generate Cursor hook scripts and ``.cursor/hooks.json`` config.

    Creates ``.cursor/hooks/`` with 3 scripts (bash on Unix, PowerShell on
    Windows) and merges hook entries into ``.cursor/hooks.json``.

    Args:
        project_root: Target project root directory.
        force_windows: Override platform detection for testing.
            ``None`` (default) auto-detects via ``sys.platform``.
        engagement_level: high (MUST/REQUIRED), medium (current), low (Consider).

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
            text = _hook_content_for_engagement(content, engagement_level)
            script_path.write_text(text, encoding="utf-8")
            if not win:
                script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
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
            existing_hooks[event] = list(entries)
            hooks_added += 1

    # Replace wrong-platform tapps commands in existing events
    hooks_migrated = 0
    for event, entries in existing_hooks.items():
        for i, entry in enumerate(entries):
            cmd = entry.get("command", "")
            if _is_wrong_platform_command(cmd, win=win) and event in hooks_config:
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


def generate_memory_capture_hook(
    project_root: Path,
    *,
    force_windows: bool | None = None,
) -> dict[str, Any]:
    """Generate the memory-capture Stop hook script and settings entry.

    Writes the ``tapps-memory-capture`` script into ``.claude/hooks/`` and
    merges a Stop hook entry into ``.claude/settings.json``.

    This is opt-in via ``memory_capture=True`` in ``tapps_init``.

    Args:
        project_root: Target project root directory.
        force_windows: Override platform detection for testing.

    Returns a summary dict with ``script_created`` and ``hooks_action``.
    """
    win = force_windows if force_windows is not None else _is_windows()

    # Select platform-appropriate script and config
    if win:
        script_name = "tapps-memory-capture.ps1"
        script_content = _CLAUDE_HOOK_SCRIPTS_PS[script_name]
        hooks_config = _MEMORY_CAPTURE_HOOKS_CONFIG_PS
    else:
        script_name = "tapps-memory-capture.sh"
        script_content = _CLAUDE_HOOK_SCRIPTS[script_name]
        hooks_config = _MEMORY_CAPTURE_HOOKS_CONFIG

    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    script_path = hooks_dir / script_name
    script_path.write_text(script_content, encoding="utf-8")
    if not win:
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

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
            existing_hooks[event] = list(entries)
            hooks_added += len(entries)
        else:
            # Check if memory capture hook is already registered
            existing_cmds: set[str] = set()
            for me in existing_hooks[event]:
                if isinstance(me, dict):
                    for h in me.get("hooks", [me]):
                        if isinstance(h, dict):
                            existing_cmds.add(h.get("command", ""))
            for entry in entries:
                entry_cmds: set[str] = set()
                for h in entry.get("hooks", [entry]):
                    if isinstance(h, dict):
                        entry_cmds.add(h.get("command", ""))
                if not entry_cmds & existing_cmds:
                    existing_hooks[event].append(entry)
                    hooks_added += 1

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    return {
        "script_created": script_name,
        "hooks_action": "created" if hooks_added > 0 else "skipped",
        "hooks_added": hooks_added,
    }


def generate_memory_auto_recall_hook(
    project_root: Path,
    *,
    force_windows: bool | None = None,
    max_results: int = 5,
    min_score: float = 0.3,
    min_prompt_length: int = 50,
) -> dict[str, Any]:
    """Generate the memory auto-recall hook (Epic 65.4).

    Writes ``tapps-memory-auto-recall`` script into ``.claude/hooks/`` and
    merges SessionStart and PreCompact entries into ``.claude/settings.json``.
    Injects relevant memories before agent prompt.

    Opt-in via ``memory_hooks.auto_recall.enabled`` in ``.tapps-mcp.yaml``.

    Args:
        project_root: Target project root directory.
        force_windows: Override platform detection for testing.
        max_results: Max memories to inject (1-10). Default: 5.
        min_score: Minimum confidence filter (0-1). Default: 0.3.
        min_prompt_length: Skip recall if query shorter than N chars. Default: 50.

    Returns a summary dict with script_created, hooks_action, hooks_added.
    """
    win = force_windows if force_windows is not None else _is_windows()
    max_results = max(1, min(max_results, 10))
    min_score = max(0.0, min(min_score, 1.0))
    min_prompt_length = max(0, min_prompt_length)

    if win:
        script_name = "tapps-memory-auto-recall.ps1"
        script_content = _memory_auto_recall_script_ps_fn(
            max_results=max_results,
            min_score=min_score,
            min_prompt_length=min_prompt_length,
        )
        hooks_config = _MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS
    else:
        script_name = "tapps-memory-auto-recall.sh"
        script_content = _memory_auto_recall_script_fn(
            max_results=max_results,
            min_score=min_score,
            min_prompt_length=min_prompt_length,
        )
        hooks_config = _MEMORY_AUTO_RECALL_HOOKS_CONFIG

    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    script_path = hooks_dir / script_name
    script_path.write_text(script_content, encoding="utf-8")
    if not win:
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

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
            existing_hooks[event] = list(entries)
            hooks_added += len(entries)
        else:
            existing_cmds: set[str] = set()
            for me in existing_hooks[event]:
                if isinstance(me, dict):
                    for h in me.get("hooks", [me]):
                        if isinstance(h, dict):
                            existing_cmds.add(h.get("command", ""))
            for entry in entries:
                entry_cmds: set[str] = set()
                for h in entry.get("hooks", [entry]):
                    if isinstance(h, dict):
                        entry_cmds.add(h.get("command", ""))
                if not entry_cmds & existing_cmds:
                    existing_hooks[event].append(entry)
                    hooks_added += 1

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    return {
        "script_created": script_name,
        "hooks_action": "created" if hooks_added > 0 else "skipped",
        "hooks_added": hooks_added,
    }


def generate_memory_auto_capture_hook(
    project_root: Path,
    *,
    force_windows: bool | None = None,
) -> dict[str, Any]:
    """Generate the memory auto-capture Stop hook (Epic 65.5).

    Writes ``tapps-memory-auto-capture`` script into ``.claude/hooks/`` and
    merges a Stop hook entry into ``.claude/settings.json``. Extracts durable
    facts from context on session stop and saves via MemoryStore.

    Opt-in via ``memory_auto_capture=True`` in ``tapps_init``.

    Args:
        project_root: Target project root directory.
        force_windows: Override platform detection for testing.

    Returns a summary dict with ``script_created`` and ``hooks_action``.
    """
    win = force_windows if force_windows is not None else _is_windows()

    if win:
        script_name = "tapps-memory-auto-capture.ps1"
        script_content = _CLAUDE_HOOK_SCRIPTS_PS[script_name]
        hooks_config = _MEMORY_AUTO_CAPTURE_HOOKS_CONFIG_PS
    else:
        script_name = "tapps-memory-auto-capture.sh"
        script_content = _CLAUDE_HOOK_SCRIPTS[script_name]
        hooks_config = _MEMORY_AUTO_CAPTURE_HOOKS_CONFIG

    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    script_path = hooks_dir / script_name
    script_path.write_text(script_content, encoding="utf-8")
    if not win:
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

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
            existing_hooks[event] = list(entries)
            hooks_added += len(entries)
        else:
            existing_cmds: set[str] = set()
            for me in existing_hooks[event]:
                if isinstance(me, dict):
                    for h in me.get("hooks", [me]):
                        if isinstance(h, dict):
                            existing_cmds.add(h.get("command", ""))
            for entry in entries:
                entry_cmds: set[str] = set()
                for h in entry.get("hooks", [entry]):
                    if isinstance(h, dict):
                        entry_cmds.add(h.get("command", ""))
                if not entry_cmds & existing_cmds:
                    existing_hooks[event].append(entry)
                    hooks_added += 1

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    return {
        "script_created": script_name,
        "hooks_action": "created" if hooks_added > 0 else "skipped",
        "hooks_added": hooks_added,
    }
