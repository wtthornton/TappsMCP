"""Hook generation logic for Claude Code and Cursor.

Creates hook script files and merges hook configuration into platform
settings files. Extracted from ``platform_generators.py`` to reduce file size.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import stat
import sys
import time
from pathlib import Path
from typing import Any

from tapps_mcp import __version__ as _tapps_version
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
    CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG as _CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS as _CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS,
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
    INVALID_CLAUDE_HOOK_KEYS as _INVALID_CLAUDE_HOOK_KEYS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_CACHE_GATE_HOOKS_CONFIG as _LINEAR_CACHE_GATE_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_CACHE_GATE_HOOKS_CONFIG_PS as _LINEAR_CACHE_GATE_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_GATE_HOOKS_CONFIG as _LINEAR_GATE_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_GATE_HOOKS_CONFIG_PS as _LINEAR_GATE_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_GATE_SCRIPTS as _LINEAR_GATE_SCRIPTS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_GATE_SCRIPTS_PS as _LINEAR_GATE_SCRIPTS_PS,
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
    PROMPT_HOOK_CONFIG as _PROMPT_HOOK_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    PS1_PREFIX,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    SESSION_START_GATE_HOOKS_CONFIG as _SESSION_START_GATE_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    SESSION_START_GATE_HOOKS_CONFIG_PS as _SESSION_START_GATE_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    SUPPORTED_CURSOR_HOOK_KEYS as _SUPPORTED_CURSOR_HOOK_KEYS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    TAPPS_MANAGED_CURSOR_HOOK_KEYS as _TAPPS_MANAGED_CURSOR_HOOK_KEYS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    _mcp_zombie_cleanup_standalone_script as _mcp_zombie_cleanup_standalone_script_fn,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    _memory_auto_recall_script as _memory_auto_recall_script_fn,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    _memory_auto_recall_script_cursor as _memory_auto_recall_script_cursor_fn,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    _memory_auto_recall_script_cursor_ps as _memory_auto_recall_script_cursor_ps_fn,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    _memory_auto_recall_script_ps as _memory_auto_recall_script_ps_fn,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    render_cache_gate_scripts as _render_cache_gate_scripts,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    render_session_start_gate_scripts as _render_session_start_gate_scripts,
)


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
        "tapps-post-validate": "PostToolUse",
        "tapps-post-report": "PostToolUse",
        "tapps-stop": "Stop",
        "tapps-task-completed": "TaskCompleted",
        "tapps-pre-compact": "PreCompact",
        "tapps-subagent-start": "SubagentStart",
        "tapps-subagent-stop": "SubagentStop",
        "tapps-session-end": "SessionEnd",
        "tapps-tool-failure": "PostToolUseFailure",
        "tapps-memory-auto-capture": "Stop",
        "tapps-pre-bash": "PreToolUse",
        # TAP-975 pipeline-state reminder
        "tapps-user-prompt-submit": "UserPromptSubmit",
        # TAP-981 Linear routing gate
        "tapps-pre-linear-write": "PreToolUse",
        "tapps-post-docs-validate": "PostToolUse",
        # TAP-1224 Linear cache-first read gate
        "tapps-pre-linear-list": "PreToolUse",
        "tapps-post-linear-snapshot-get": "PostToolUse",
        # TAP-1412 Linear list_issues auto-populate
        "tapps-post-linear-list": "PostToolUse",
        # Session-start enforcement gate
        "tapps-pre-session-start-gate": "PreToolUse",
        "tapps-post-session-start": "PostToolUse",
        # TAP-956 reactive-event scripts
        "tapps-cwd-changed": "CwdChanged",
        "tapps-permission-denied": "PermissionDenied",
        "tapps-session-title": "UserPromptSubmit",
        "tapps-worktree-create": "WorktreeCreate",
        "tapps-worktree-remove": "WorktreeRemove",
    }

    filtered: dict[str, str] = {}
    for name, content in script_templates.items():
        # Extract base name without extension
        base = name.rsplit(".", 1)[0]
        event = script_event_map.get(base, "")
        if event in allowed_events:
            filtered[name] = content
    return filtered


_HOOK_VERSION_MARKER_PREFIX = "# tapps-mcp-hook-version:"
_HOOK_VERSION_MARKER_RE = re.compile(r"^\s*#\s*tapps-mcp-hook-version:\s*([\w.+-]+)", re.MULTILINE)
_HOOK_CONTENT_SHA_RE = re.compile(
    r"^\s*#\s*tapps-mcp-hook-content-sha:\s*([0-9a-f]{8})", re.MULTILINE
)
# Scan only the top of the file — the marker is always near the shebang.
_HOOK_MARKER_SCAN_CHARS = 512


def _hook_content_sha_for_template(content: str) -> str:
    """Stable 8-char digest of hook body (pre-marker) for upgrade invalidation."""
    return hashlib.sha256(content.encode()).hexdigest()[:8]


def _inject_hook_version_marker(content: str, version: str) -> str:
    """Prepend a version marker to a hook script if it doesn't already have one.

    The marker is inserted on its own line immediately after the shebang (if
    any) so bash/PowerShell continue to parse the file correctly.
    TAP-957: lets ``_hook_has_user_edits`` tell a TappsMCP-shipped script from
    a user-authored one and avoid clobbering on upgrade.
    """
    content_sha = _hook_content_sha_for_template(content)
    if _HOOK_VERSION_MARKER_RE.search(content[:_HOOK_MARKER_SCAN_CHARS]):
        # Refresh content-sha line when rewriting an already-marked template.
        lines = content.splitlines(keepends=True)
        out: list[str] = []
        for line in lines:
            if _HOOK_CONTENT_SHA_RE.match(line):
                continue
            out.append(line)
        content = "".join(out)

    marker_line = (
        f"{_HOOK_VERSION_MARKER_PREFIX} {version}\n# tapps-mcp-hook-content-sha: {content_sha}\n"
    )
    # Preserve shebang on line 1 if present; marker goes right after.
    lines = content.splitlines(keepends=True)
    if lines and lines[0].startswith("#!"):
        return lines[0] + marker_line + "".join(lines[1:])
    return marker_line + content


def _hook_has_user_edits(path: Path) -> bool:
    """Return True if *path* looks user-authored and should be preserved.

    Heuristic: a TappsMCP-shipped hook always carries the version marker
    in its header. Absence of the marker is the strongest signal that the
    file was written or rewritten by the consuming project.
    """
    try:
        head = path.read_text(encoding="utf-8")[:_HOOK_MARKER_SCAN_CHARS]
    except (OSError, UnicodeDecodeError):
        # Unreadable / binary file — err on the side of caution.
        return True
    return _HOOK_VERSION_MARKER_RE.search(head) is None


def _hook_marker_version(path: Path) -> str | None:
    """Return the ``tapps-mcp-hook-version`` marker on disk, or None if absent."""
    try:
        head = path.read_text(encoding="utf-8")[:_HOOK_MARKER_SCAN_CHARS]
    except (OSError, UnicodeDecodeError):
        return None
    match = _HOOK_VERSION_MARKER_RE.search(head)
    return match.group(1) if match else None


def _hook_content_sha_on_disk(path: Path) -> str | None:
    """Return the content-sha marker on disk, or None if absent."""
    try:
        head = path.read_text(encoding="utf-8")[:_HOOK_MARKER_SCAN_CHARS]
    except (OSError, UnicodeDecodeError):
        return None
    match = _HOOK_CONTENT_SHA_RE.search(head)
    return match.group(1) if match else None


def _project_root_from_hooks_dir(hooks_dir: Path) -> Path:
    """Return the repo root for ``.claude/hooks`` or ``.cursor/hooks``."""
    if hooks_dir.parent.name in (".claude", ".cursor"):
        return hooks_dir.parent.parent
    return hooks_dir.parent


def _hook_backup_storage_dir(project_root: Path, hooks_dir: Path) -> Path:
    """Directory for pre-upgrade hook copies (outside the live hooks folder)."""
    try:
        rel = hooks_dir.relative_to(project_root)
    except ValueError:
        rel = Path("hooks")
    return project_root / ".tapps-mcp" / "hook-backups" / rel


def _backup_hook_file(path: Path, *, project_root: Path | None = None) -> Path:
    """Copy *path* to ``.tapps-mcp/hook-backups/.../<name>.pre-upgrade.<ts>``."""
    ts = int(time.time())
    root = project_root or _project_root_from_hooks_dir(path.parent)
    backup_dir = _hook_backup_storage_dir(root, path.parent)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.name}.pre-upgrade.{ts}"
    shutil.copy2(path, backup)
    return backup


def _prune_hook_pre_upgrade_backups(storage_dir: Path, *, keep: int = 2) -> list[str]:
    """Drop stale ``*.pre-upgrade.<ts>`` copies after hook upgrades (TAP-3584 follow-up)."""
    from collections import defaultdict

    if not storage_dir.is_dir():
        return []

    groups: dict[str, list[Path]] = defaultdict(list)
    for path in storage_dir.iterdir():
        name = path.name
        if ".pre-upgrade." not in name:
            continue
        base = name.split(".pre-upgrade.", 1)[0]
        groups[base].append(path)

    removed: list[str] = []
    for paths in groups.values():
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in paths[keep:]:
            stale.unlink(missing_ok=True)
            removed.append(stale.name)
    return removed


def _prune_legacy_co_located_hook_backups(hooks_dir: Path) -> list[str]:
    """Remove legacy ``*.pre-upgrade.*`` sidecars still sitting in the hooks dir."""
    removed: list[str] = []
    for stale in hooks_dir.glob("*.pre-upgrade.*"):
        stale.unlink(missing_ok=True)
        removed.append(stale.name)
    return removed


def _list_stale_pre_upgrade_backups(storage_dir: Path, *, keep: int = 2) -> list[str]:
    """Return backup filenames that ``_prune_hook_pre_upgrade_backups`` would delete."""
    from collections import defaultdict

    if not storage_dir.is_dir():
        return []
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in storage_dir.iterdir():
        name = path.name
        if ".pre-upgrade." not in name:
            continue
        base = name.split(".pre-upgrade.", 1)[0]
        groups[base].append(path)

    stale_names: list[str] = []
    for paths in groups.values():
        paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        stale_names.extend(stale.name for stale in paths[keep:])
    return stale_names


def cleanup_legacy_hook_sidecars(
    project_root: Path,
    *,
    dry_run: bool = False,
    prune_storage_keep: int = 2,
) -> dict[str, Any]:
    """Remove co-located ``*.pre-upgrade.*`` sidecars from hook directories.

    Before TAP-3584 follow-up, hook backups lived beside live scripts
    (``tapps-stop.sh.pre-upgrade.<ts>``). New backups go under
    ``.tapps-mcp/hook-backups/``. This helper deletes the legacy sidecars and
    prunes excess copies in the new storage tree.

    Safe to run standalone via ``tapps-mcp cleanup-hook-backups`` or during
    ``tapps_upgrade``.
    """
    hook_dirs = (
        project_root / ".claude" / "hooks",
        project_root / ".cursor" / "hooks",
    )
    removed_sidecars: dict[str, list[str]] = {}
    for hooks_dir in hook_dirs:
        if not hooks_dir.is_dir():
            continue
        rel = str(hooks_dir.relative_to(project_root))
        sidecars = sorted(p.name for p in hooks_dir.glob("*.pre-upgrade.*"))
        if not sidecars:
            continue
        if dry_run:
            removed_sidecars[rel] = sidecars
        else:
            removed_sidecars[rel] = _prune_legacy_co_located_hook_backups(hooks_dir)

    storage_root = project_root / ".tapps-mcp" / "hook-backups"
    pruned_storage: dict[str, list[str]] = {}
    if storage_root.is_dir():
        for storage_dir in storage_root.rglob("*"):
            if not storage_dir.is_dir():
                continue
            stale = _list_stale_pre_upgrade_backups(storage_dir, keep=prune_storage_keep)
            if not stale:
                continue
            rel = str(storage_dir.relative_to(project_root))
            if dry_run:
                pruned_storage[rel] = stale
            else:
                pruned_storage[rel] = _prune_hook_pre_upgrade_backups(
                    storage_dir,
                    keep=prune_storage_keep,
                )

    total_sidecars = sum(len(v) for v in removed_sidecars.values())
    total_pruned = sum(len(v) for v in pruned_storage.values())
    action = "dry-run" if dry_run else "cleaned"
    return {
        "action": action,
        "removed_sidecars": removed_sidecars,
        "pruned_storage": pruned_storage,
        "removed_sidecar_count": total_sidecars,
        "pruned_storage_count": total_pruned,
    }


def _write_hook_scripts(
    hooks_dir: Path,
    script_templates: dict[str, str],
    engagement_level: str,
    win: bool,
) -> list[str]:
    """Write hook scripts to disk, returning names of scripts created.

    TAP-957: every shipped script carries a version marker. When a hook file
    already on disk is missing the marker (sign of user edits), it is copied
    to ``<name>.pre-upgrade.<ts>`` before being rewritten so the user's work
    is recoverable.
    """
    always_overwrite = {
        "tapps-stop.ps1",
        "tapps-stop.sh",
        "tapps-task-completed.ps1",
        "tapps-task-completed.sh",
    }
    project_root = _project_root_from_hooks_dir(hooks_dir)
    backup_dir = _hook_backup_storage_dir(project_root, hooks_dir)
    created: list[str] = []
    for name, content in script_templates.items():
        script_path = hooks_dir / name
        if script_path.exists() and name not in always_overwrite:
            # TAP-1325 / v3.9.0: rewrite when the deployed marker version
            # differs from the running tapps-mcp version. Without this, hook
            # content updates landing in a release never reach consumer
            # projects unless the hook is in ``always_overwrite``.
            on_disk_version = _hook_marker_version(script_path)
            template_sha = _hook_content_sha_for_template(content)
            on_disk_sha = _hook_content_sha_on_disk(script_path)
            if on_disk_version == _tapps_version and on_disk_sha == template_sha:
                continue
            # No marker → user-authored, fall through to the user-edits path
            # below. Marker present but stale → back up before rewriting.
            if on_disk_version is not None:
                _backup_hook_file(script_path, project_root=project_root)
        # If an existing file lacks the marker, preserve user edits first.
        if script_path.exists() and _hook_has_user_edits(script_path):
            _backup_hook_file(script_path, project_root=project_root)
        text = _hook_content_for_engagement(content, engagement_level)
        text = _inject_hook_version_marker(text, _tapps_version)
        script_path.write_text(text, encoding="utf-8")
        if not win:
            script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        created.append(name)
    _prune_hook_pre_upgrade_backups(backup_dir)
    _prune_legacy_co_located_hook_backups(hooks_dir)
    return created


def _cleanup_wrong_platform_scripts(hooks_dir: Path, win: bool) -> list[str]:
    """Remove hook scripts with the wrong platform extension."""
    wrong_ext = ".sh" if win else ".ps1"
    removed: list[str] = []
    for old_script in hooks_dir.glob(f"tapps-*{wrong_ext}"):
        old_script.unlink()
        removed.append(old_script.name)
    return removed


class ManagedJsonError(ValueError):
    """A tapps-managed JSON config (settings.json / hooks.json) failed to parse.

    Carries the offending path plus a remediation hint so the upgrade pipeline
    can report which file is broken and how to repair it, instead of aborting an
    entire platform scope with a bare ``Extra data`` traceback.
    """

    def __init__(self, path: Path, original: json.JSONDecodeError) -> None:
        self.path = path
        self.original = original
        self.remediation = (
            "Repair the file (a common cause is a missing opening '{' brace or a "
            "leading byte-order mark) or restore it from a .tapps-mcp backup, then "
            "re-run `tapps-mcp upgrade`. Run `tapps-mcp doctor` to confirm it parses."
        )
        super().__init__(
            f"{path}: invalid JSON — {original.msg} "
            f"(line {original.lineno}, column {original.colno})"
        )


def _load_managed_json(path: Path) -> dict[str, Any]:
    """Load a tapps-managed JSON config, returning ``{}`` when absent or empty.

    Raises :class:`ManagedJsonError` on a parse failure so callers can surface a
    file-scoped, actionable error rather than letting a bare ``JSONDecodeError``
    abort the whole upgrade scope.
    """
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManagedJsonError(path, exc) from exc
    return data if isinstance(data, dict) else {}


def _write_managed_json(path: Path, data: dict[str, Any]) -> None:
    """Write a tapps-managed JSON config with a round-trip sanity check.

    Serializes with ``json.dumps``, verifies the output parses back through
    ``json.loads`` before touching disk, then writes UTF-8 text. Catches generator
    bugs that would emit a document missing its opening ``{`` brace.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2) + "\n"
    json.loads(text)
    path.write_text(text, encoding="utf-8")


def dry_run_managed_json_status(path: Path, *, ok_message: str) -> str | dict[str, Any]:
    """Dry-run helper: parse the real managed JSON file or return an error dict."""
    if not path.exists():
        return ok_message
    try:
        _load_managed_json(path)
    except ManagedJsonError as exc:
        return {"action": "error", "error": str(exc), "hint": exc.remediation}
    return ok_message


def _merge_hooks_config(
    existing_hooks: dict[str, Any],
    hooks_config: dict[str, Any],
) -> int:
    """Merge new hook entries into existing hooks, returning count of entries added."""
    added = 0
    for event, entries in hooks_config.items():
        if event not in existing_hooks:
            existing_hooks[event] = list(entries)
            added += len(entries)
        else:
            existing_matchers = {
                e.get("matcher") for e in existing_hooks[event] if isinstance(e, dict)
            }
            for entry in entries:
                if entry.get("matcher") not in existing_matchers:
                    existing_hooks[event].append(entry)
                    added += 1
    return added


def _add_prompt_hooks(existing_hooks: dict[str, Any]) -> int:
    """Add prompt-type PostToolUse hooks if not already present. Returns count added."""
    prompt_entries = _PROMPT_HOOK_CONFIG.get("PostToolUse", [])
    if "PostToolUse" not in existing_hooks:
        existing_hooks["PostToolUse"] = list(prompt_entries)
        return len(prompt_entries)
    has_prompt = any(
        e.get("type") == "prompt" for e in existing_hooks["PostToolUse"] if isinstance(e, dict)
    )
    if not has_prompt:
        existing_hooks["PostToolUse"].extend(prompt_entries)
        return len(prompt_entries)
    return 0


def generate_claude_hooks(
    project_root: Path,
    *,
    force_windows: bool | None = None,
    engagement_level: str = "medium",
    prompt_hooks: bool = False,
    destructive_guard: bool = False,
    linear_enforce_gate: bool = False,
    linear_enforce_cache_gate: str = "off",
    session_start_gate: str = "off",
    reactive_hooks: dict[str, bool] | None = None,
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
    # TAP-981/TAP-986: Linear routing gate — independent of destructive_guard.
    # Adds both PreToolUse (blocks raw save_issue) and PostToolUse (sentinel
    # writer after docs_validate_linear_issue). Bash + PowerShell variants
    # ship together; the branch below picks the right pair for the platform.
    linear_gate_active = linear_enforce_gate
    if linear_gate_active:
        allowed_events.add("PreToolUse")
        allowed_events.add("PostToolUse")
    # TAP-1224: cache-first read gate. "off" (default) installs nothing;
    # "warn" / "block" install the post-snapshot-get sentinel writer + the
    # pre-list gate, with the mode baked into the pre-list script.
    cache_gate_mode = (
        linear_enforce_cache_gate
        if linear_enforce_cache_gate in ("off", "warn", "block")
        else "off"
    )
    cache_gate_active = cache_gate_mode in ("warn", "block")
    if cache_gate_active:
        allowed_events.add("PreToolUse")
        allowed_events.add("PostToolUse")
    # Session-start enforcement gate. "off" (default) installs nothing; "warn"
    # logs violations and allows; "block" exits 2 on any TappsMCP quality tool
    # called before tapps_session_start ran this session. The mode is baked
    # into the pre-gate script; the sentinel writer is mode-independent.
    session_gate_mode = (
        session_start_gate if session_start_gate in ("off", "warn", "block") else "off"
    )
    session_gate_active = session_gate_mode in ("warn", "block")
    if session_gate_active:
        allowed_events.add("PreToolUse")
        allowed_events.add("PostToolUse")

    # Select base scripts and config. Deep-copy the hooks config so the
    # opt-in-gate extend()s below mutate our local copy, not the module-level
    # template dict — otherwise the first caller that enables destructive_guard
    # or linear_enforce_gate permanently pollutes subsequent calls (TAP-987).
    base_scripts = _CLAUDE_HOOK_SCRIPTS_PS if win else _CLAUDE_HOOK_SCRIPTS
    hooks_config = copy.deepcopy(_CLAUDE_HOOKS_CONFIG_PS if win else _CLAUDE_HOOKS_CONFIG)
    if destructive_guard:
        dg_config = _DESTRUCTIVE_GUARD_HOOKS_CONFIG_PS if win else _DESTRUCTIVE_GUARD_HOOKS_CONFIG
        for event, entries in dg_config.items():
            hooks_config.setdefault(event, []).extend(entries)
    if linear_gate_active:
        lg_scripts = _LINEAR_GATE_SCRIPTS_PS if win else _LINEAR_GATE_SCRIPTS
        lg_config = _LINEAR_GATE_HOOKS_CONFIG_PS if win else _LINEAR_GATE_HOOKS_CONFIG
        base_scripts = {**base_scripts, **lg_scripts}
        for event, entries in lg_config.items():
            hooks_config.setdefault(event, []).extend(entries)
    if cache_gate_active:
        cg_scripts = _render_cache_gate_scripts(cache_gate_mode, win=win)
        cg_config = _LINEAR_CACHE_GATE_HOOKS_CONFIG_PS if win else _LINEAR_CACHE_GATE_HOOKS_CONFIG
        base_scripts = {**base_scripts, **cg_scripts}
        for event, entries in cg_config.items():
            hooks_config.setdefault(event, []).extend(entries)
    if session_gate_active:
        sg_scripts = _render_session_start_gate_scripts(session_gate_mode, win=win)
        sg_config = _SESSION_START_GATE_HOOKS_CONFIG_PS if win else _SESSION_START_GATE_HOOKS_CONFIG
        base_scripts = {**base_scripts, **sg_scripts}
        for event, entries in sg_config.items():
            hooks_config.setdefault(event, []).extend(entries)

    # TAP-956: opt-in reactive-event hooks (CwdChanged, PermissionDenied,
    # sessionTitle, Worktree*). Each flag independently ships its script +
    # hooks.json entry; unrelated flags remain off.
    reactive_flags = reactive_hooks or {}
    if reactive_flags:
        from tapps_mcp.pipeline.platform_hook_templates import (
            reactive_hook_scripts as _reactive_hook_scripts,
        )
        from tapps_mcp.pipeline.platform_hook_templates import (
            reactive_hooks_config as _reactive_hooks_config,
        )

        base_scripts = {
            **base_scripts,
            **_reactive_hook_scripts(reactive_flags, win=win),
        }
        for event, entries in _reactive_hooks_config(reactive_flags, win=win).items():
            hooks_config.setdefault(event, []).extend(entries)
            allowed_events.add(event)

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

    scripts_created = _write_hook_scripts(hooks_dir, script_templates, engagement_level, win)
    scripts_removed = _cleanup_wrong_platform_scripts(hooks_dir, win)

    # Load or init .claude/settings.json
    settings_file = project_root / ".claude" / "settings.json"
    config: dict[str, Any] = _load_managed_json(settings_file)

    existing_hooks: dict[str, Any] = config.setdefault("hooks", {})
    hooks_added = _merge_hooks_config(existing_hooks, hooks_config)

    # Add prompt-type hook if opted-in
    if prompt_hooks and "PostToolUse" in allowed_events:
        hooks_added += _add_prompt_hooks(existing_hooks)

    hooks_migrated = _migrate_claude_hook_commands(existing_hooks, hooks_config, win=win)

    # Only write hook keys supported by Claude Code schema
    config["hooks"] = {
        k: v for k, v in config["hooks"].items() if k not in _INVALID_CLAUDE_HOOK_KEYS
    }

    _write_managed_json(settings_file, config)

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
        "linear_enforce_gate": linear_gate_active,
        "linear_enforce_cache_gate": cache_gate_mode,
        "session_start_gate": session_gate_mode,
    }


def _parse_cursor_hooks_file(hooks_file: Path) -> dict[str, Any]:
    """Load ``.cursor/hooks.json`` or return an empty config dict."""
    return _load_managed_json(hooks_file)


def _normalize_cursor_hooks_raw(config: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Return the ``hooks`` object in Cursor's dict format, migrating legacy arrays."""
    existing_hooks_raw = config.get("hooks", {})
    if isinstance(existing_hooks_raw, list):
        migrated: dict[str, list[dict[str, str]]] = {}
        for entry in existing_hooks_raw:
            if isinstance(entry, dict) and "event" in entry:
                event = entry["event"]
                cmd_obj = {k: v for k, v in entry.items() if k != "event"}
                migrated.setdefault(event, []).append(cmd_obj)
        return migrated
    if isinstance(existing_hooks_raw, dict):
        return existing_hooks_raw
    return {}


def merge_cursor_hooks_config(
    existing_hooks: dict[str, list[dict[str, str]]],
    hooks_config: dict[str, list[dict[str, str]]],
    *,
    win: bool,
) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    """Merge TappsMCP hook entries into existing Cursor hooks.

    Preserves every pre-existing event key (third-party / skill hooks). Only
    adds missing Tapps-owned events and migrates wrong-platform tapps commands.
    """
    merged = dict(existing_hooks)

    hooks_added = 0
    for event, entries in hooks_config.items():
        if event not in merged:
            merged[event] = list(entries)
            hooks_added += 1

    hooks_migrated = 0
    for event, entries in merged.items():
        for i, entry in enumerate(entries):
            cmd = entry.get("command", "")
            if _is_wrong_platform_command(cmd, win=win) and event in hooks_config:
                merged[event][i] = hooks_config[event][0]
                hooks_migrated += 1

    third_party_keys = sorted(k for k in merged if k not in _TAPPS_MANAGED_CURSOR_HOOK_KEYS)
    unknown_keys = sorted(k for k in merged if k not in _SUPPORTED_CURSOR_HOOK_KEYS)
    stats: dict[str, Any] = {
        "hooks_added": hooks_added,
        "hooks_migrated": hooks_migrated,
        "third_party_hook_keys": third_party_keys,
        "unknown_hook_keys": unknown_keys,
        "preserved_hook_keys": sorted(merged.keys()),
    }
    return merged, stats


def preview_cursor_hooks_merge(
    project_root: Path,
    *,
    force_windows: bool | None = None,
) -> dict[str, Any]:
    """Simulate hooks.json merge without writing (for upgrade dry-run)."""
    win = force_windows if force_windows is not None else _is_windows()
    hooks_config = _CURSOR_HOOKS_CONFIG_PS if win else _CURSOR_HOOKS_CONFIG
    hooks_file = project_root / ".cursor" / "hooks.json"
    config = _parse_cursor_hooks_file(hooks_file)
    existing_hooks = _normalize_cursor_hooks_raw(config)
    before_keys = set(existing_hooks.keys())
    merged, stats = merge_cursor_hooks_config(existing_hooks, hooks_config, win=win)
    after_keys = set(merged.keys())
    removed_keys = sorted(before_keys - after_keys)
    stats["removed_hook_keys"] = removed_keys
    stats["would_remove_keys"] = removed_keys
    return stats


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

    scripts_created = _write_hook_scripts(hooks_dir, script_templates, engagement_level, win)
    scripts_removed = _cleanup_wrong_platform_scripts(hooks_dir, win)

    # Merge hooks config into .cursor/hooks.json
    hooks_file = project_root / ".cursor" / "hooks.json"
    config = _parse_cursor_hooks_file(hooks_file)

    existing_hooks = _normalize_cursor_hooks_raw(config)
    existing_hooks, merge_stats = merge_cursor_hooks_config(existing_hooks, hooks_config, win=win)
    hooks_added = merge_stats["hooks_added"]
    hooks_migrated = merge_stats["hooks_migrated"]

    config["hooks"] = existing_hooks
    config["version"] = 1
    _write_managed_json(hooks_file, config)

    action = "migrated" if hooks_migrated > 0 else ("created" if hooks_added > 0 else "skipped")
    return {
        "scripts_created": scripts_created,
        "scripts_removed": scripts_removed,
        "hooks_action": action,
        "hooks_added": hooks_added,
        "hooks_migrated": hooks_migrated,
        "third_party_hook_keys": merge_stats["third_party_hook_keys"],
        "unknown_hook_keys": merge_stats["unknown_hook_keys"],
        "preserved_hook_keys": merge_stats["preserved_hook_keys"],
        "removed_hook_keys": [],
    }


def generate_memory_auto_recall_hook(
    project_root: Path,
    *,
    force_windows: bool | None = None,
    max_results: int = 5,
    min_score: float = 0.3,
    min_prompt_length: int = 50,
    recall_keys: list[str] | None = None,
    platform: str = "claude",
) -> dict[str, Any]:
    """Generate the memory auto-recall hook (Epic 65.4).

    Claude: writes into ``.claude/hooks/`` and merges SessionStart/PreCompact
    entries into ``.claude/settings.json``.

    Cursor: writes into ``.cursor/hooks/`` and merges sessionStart/preCompact
    into ``.cursor/hooks.json``.

    Opt-in via ``memory_hooks.auto_recall.enabled`` in ``.tapps-mcp.yaml``.
    """
    win = force_windows if force_windows is not None else _is_windows()
    max_results = max(1, min(max_results, 10))
    min_score = max(0.0, min(min_score, 1.0))
    min_prompt_length = max(0, min_prompt_length)
    keys = list(recall_keys or [])

    if platform == "cursor":
        return _generate_cursor_memory_auto_recall_hook(
            project_root,
            win=win,
            max_results=max_results,
            min_score=min_score,
            min_prompt_length=min_prompt_length,
            recall_keys=keys,
        )

    if win:
        script_name = "tapps-memory-auto-recall.ps1"
        script_content = _memory_auto_recall_script_ps_fn(
            max_results=max_results,
            min_score=min_score,
            min_prompt_length=min_prompt_length,
            recall_keys=keys,
        )
        hooks_config = _MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS
    else:
        script_name = "tapps-memory-auto-recall.sh"
        script_content = _memory_auto_recall_script_fn(
            max_results=max_results,
            min_score=min_score,
            min_prompt_length=min_prompt_length,
            recall_keys=keys,
        )
        hooks_config = _MEMORY_AUTO_RECALL_HOOKS_CONFIG

    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    script_path = hooks_dir / script_name
    script_path.write_text(script_content, encoding="utf-8")
    if not win:
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

    settings_file = project_root / ".claude" / "settings.json"
    config: dict[str, Any] = _load_managed_json(settings_file)

    existing_hooks: dict[str, Any] = config.setdefault("hooks", {})
    hooks_added = _merge_claude_memory_hook_entries(existing_hooks, hooks_config)

    config["hooks"] = {
        k: v for k, v in config["hooks"].items() if k not in _INVALID_CLAUDE_HOOK_KEYS
    }
    _write_managed_json(settings_file, config)

    return {
        "script_created": script_name,
        "hooks_action": "created" if hooks_added > 0 else "skipped",
        "hooks_added": hooks_added,
        "platform": platform,
    }


def _merge_claude_memory_hook_entries(
    existing_hooks: dict[str, Any],
    hooks_config: dict[str, list[dict[str, Any]]],
) -> int:
    """Merge memory hook entries into Claude settings without duplicating commands."""
    hooks_added = 0
    for event, entries in hooks_config.items():
        if event not in existing_hooks:
            existing_hooks[event] = list(entries)
            hooks_added += len(entries)
            continue
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
    return hooks_added


def _merge_cursor_hook_command_entries(
    existing_hooks: dict[str, list[dict[str, str]]],
    hooks_config: dict[str, list[dict[str, str]]],
    *,
    win: bool,
) -> int:
    """Append Tapps hook commands per event without duplicating command paths."""
    hooks_added = 0
    for event, entries in hooks_config.items():
        if event not in existing_hooks:
            existing_hooks[event] = list(entries)
            hooks_added += len(entries)
            continue
        existing_hooks[event] = [
            entry
            for entry in existing_hooks[event]
            if isinstance(entry, dict)
            and not _is_wrong_platform_command(entry.get("command", ""), win=win)
        ]
        existing_cmds = {
            entry.get("command", "") for entry in existing_hooks[event] if isinstance(entry, dict)
        }
        for entry in entries:
            cmd = entry.get("command", "")
            if cmd and cmd not in existing_cmds:
                existing_hooks[event].append(entry)
                existing_cmds.add(cmd)
                hooks_added += 1
    return hooks_added


def _strip_cursor_zombie_cleanup_hooks(
    existing_hooks: dict[str, list[dict[str, str]]],
) -> bool:
    """Remove deprecated sessionStart zombie cleanup (deploy-local only now)."""
    entries = existing_hooks.get("sessionStart")
    if not isinstance(entries, list) or not entries:
        return False
    zombie_cmds = {
        ".cursor/hooks/tapps-mcp-zombie-cleanup.sh",
        PS1_PREFIX + ".cursor/hooks/tapps-mcp-zombie-cleanup.ps1",
    }
    filtered = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("command", "") not in zombie_cmds
    ]
    if filtered == entries:
        return False
    existing_hooks["sessionStart"] = filtered
    return True


def _ensure_cursor_session_start_order(
    existing_hooks: dict[str, list[dict[str, str]]],
) -> bool:
    """Strip legacy zombie cleanup from sessionStart; recall-only is correct."""
    return _strip_cursor_zombie_cleanup_hooks(existing_hooks)


def _generate_cursor_memory_auto_recall_hook(
    project_root: Path,
    *,
    win: bool,
    max_results: int,
    min_score: float,
    min_prompt_length: int,
    recall_keys: list[str],
) -> dict[str, Any]:
    """Write Cursor memory auto-recall script and merge hooks.json entries."""
    zombie_script_name = "tapps-mcp-zombie-cleanup.ps1" if win else "tapps-mcp-zombie-cleanup.sh"
    if win:
        script_name = "tapps-memory-auto-recall.ps1"
        script_content = _memory_auto_recall_script_cursor_ps_fn(
            max_results=max_results,
            min_score=min_score,
            min_prompt_length=min_prompt_length,
            recall_keys=recall_keys,
        )
        zombie_script_content = (
            "# TappsMCP MCP zombie cleanup (Windows stub — run upgrade on Windows)\nexit 0\n"
        )
        hooks_config = _CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS
    else:
        script_name = "tapps-memory-auto-recall.sh"
        script_content = _memory_auto_recall_script_cursor_fn(
            max_results=max_results,
            min_score=min_score,
            min_prompt_length=min_prompt_length,
            recall_keys=recall_keys,
        )
        zombie_script_content = _mcp_zombie_cleanup_standalone_script_fn()
        hooks_config = _CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG

    hooks_dir = project_root / ".cursor" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    zombie_script_path = hooks_dir / zombie_script_name
    zombie_script_path.write_text(zombie_script_content, encoding="utf-8")
    script_path = hooks_dir / script_name
    script_path.write_text(script_content, encoding="utf-8")
    if not win:
        zombie_script_path.chmod(zombie_script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

    hooks_file = project_root / ".cursor" / "hooks.json"
    config = _parse_cursor_hooks_file(hooks_file)
    existing_hooks = _normalize_cursor_hooks_raw(config)
    hooks_added = _merge_cursor_hook_command_entries(existing_hooks, hooks_config, win=win)
    hooks_reordered = _ensure_cursor_session_start_order(existing_hooks)

    config["hooks"] = existing_hooks
    config["version"] = 1
    _write_managed_json(hooks_file, config)

    return {
        "script_created": script_name,
        "zombie_cleanup_script_created": zombie_script_name,
        "scripts_refreshed": [zombie_script_name, script_name],
        "hooks_action": "created" if hooks_added > 0 or hooks_reordered else "refreshed",
        "hooks_added": hooks_added,
        "hooks_reordered": hooks_reordered,
        "platform": "cursor",
    }


def wire_memory_hooks(
    project_root: Path,
    *,
    platform: str,
    memory_auto_recall: bool = False,
    memory_auto_capture: bool = False,
    force_windows: bool | None = None,
) -> dict[str, Any]:
    """Install memory auto-recall/capture hooks from ``memory_hooks`` settings."""
    result: dict[str, Any] = {}
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings(project_root=project_root)
        mh = settings.memory_hooks
        if memory_auto_recall or mh.auto_recall.enabled:
            result["memory_auto_recall"] = generate_memory_auto_recall_hook(
                project_root,
                force_windows=force_windows,
                max_results=mh.auto_recall.max_results,
                min_score=mh.auto_recall.min_score,
                min_prompt_length=mh.auto_recall.min_prompt_length,
                recall_keys=list(mh.auto_recall.recall_keys),
                platform=platform,
            )
        if platform == "claude" and (memory_auto_capture or mh.auto_capture.enabled):
            result["memory_auto_capture"] = generate_memory_auto_capture_hook(
                project_root,
                force_windows=force_windows,
            )
    except (AttributeError, ImportError, OSError) as exc:
        import structlog

        structlog.get_logger(__name__).warning("memory_hooks_probe_failed", error=str(exc))
        result["memory_hooks_error"] = str(exc)
    return result


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
    config: dict[str, Any] = _load_managed_json(settings_file)

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

    config["hooks"] = {
        k: v for k, v in config["hooks"].items() if k not in _INVALID_CLAUDE_HOOK_KEYS
    }
    _write_managed_json(settings_file, config)

    return {
        "script_created": script_name,
        "hooks_action": "created" if hooks_added > 0 else "skipped",
        "hooks_added": hooks_added,
    }
