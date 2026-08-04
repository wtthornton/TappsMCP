"""Doctor checks for Claude settings and Cursor hook wiring (TAP-5606 split).

Covers ``.claude/settings.json`` permissions + hook-key schema, managed-JSON
parseability, Cursor MCP zombie-cleanup wiring, and hook directory/config
validation. Split out of ``doctor_hooks`` to keep both modules within the
maintainability budget.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from tapps_mcp.distribution.doctor_result import CheckResult
from tapps_mcp.pipeline.platform_hook_templates import (
    SUPPORTED_CLAUDE_HOOK_KEYS,
    SUPPORTED_CURSOR_HOOK_KEYS,
)


def check_claude_settings(project_root: Path) -> CheckResult:
    """Check ``.claude/settings.json`` for permissions and hook schema validity.

    Verifies:
    - Permission entries: both ``mcp__tapps-mcp`` and ``mcp__tapps-mcp__*``
      (work around Claude Code permission bugs #3107, #13077, #27139).
    - Hook keys: only schema-supported keys (e.g. no PostCompact); invalid
      keys cause Claude Code to skip the entire settings file.
    """
    settings_file = project_root / ".claude" / "settings.json"
    if not settings_file.exists():
        return CheckResult(
            ".claude/settings.json",
            False,
            ".claude/settings.json not found",
            "Run: tapps-mcp upgrade --host claude-code",
        )
    try:
        raw = settings_file.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return CheckResult(
            ".claude/settings.json",
            False,
            "Invalid JSON in .claude/settings.json",
        )
    allow_list = data.get("permissions", {}).get("allow", [])
    required = ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]
    missing = [e for e in required if e not in allow_list]
    if missing:
        return CheckResult(
            ".claude/settings.json",
            False,
            f"Missing permission entries: {', '.join(missing)}",
            "Run: tapps-mcp upgrade --host claude-code",
        )
    # Invalid hook keys (e.g. PostCompact) cause Claude Code to skip the entire file
    hooks_obj = data.get("hooks") or {}
    if isinstance(hooks_obj, dict):
        invalid = [k for k in hooks_obj if k not in SUPPORTED_CLAUDE_HOOK_KEYS]
        if invalid:
            return CheckResult(
                ".claude/settings.json",
                False,
                f"Unsupported hook keys (Claude Code will skip file): {', '.join(sorted(invalid))}",
                "Run: tapps-mcp upgrade --host claude-code to write only supported hooks.",
            )
    return CheckResult(
        ".claude/settings.json",
        True,
        "TappsMCP permission entries present (bare + wildcard), hooks schema valid",
    )


def check_managed_json_parseable(project_root: Path) -> CheckResult:
    """Verify tapps-managed JSON configs parse cleanly.

    A malformed ``.claude/settings.json`` or ``.cursor/hooks.json`` (e.g. a
    dropped opening ``{`` brace from an external editor or a Windows BOM) makes
    ``tapps-mcp upgrade`` skip that platform's hooks merge. Catch it here with a
    one-line repair hint so the operator fixes the file before the next upgrade.
    """
    from tapps_mcp.pipeline.platform_hooks import ManagedJsonError, _load_managed_json

    name = "Managed JSON configs"
    targets = [
        project_root / ".claude" / "settings.json",
        project_root / ".cursor" / "hooks.json",
    ]
    broken: list[str] = []
    for target in targets:
        if not target.exists():
            continue
        try:
            _load_managed_json(target)
        except ManagedJsonError as exc:
            broken.append(str(exc))
    if broken:
        return CheckResult(
            name,
            False,
            "; ".join(broken),
            "Repair the file (a common cause is a missing opening '{' brace) or "
            "restore it from a .tapps-mcp backup, then re-run tapps-mcp upgrade.",
        )
    return CheckResult(name, True, ".claude/settings.json / .cursor/hooks.json parse cleanly")


def _cursor_session_start_entries(project_root: Path) -> list[dict[str, Any]] | None:
    """Return the ``hooks.sessionStart`` entry list from ``.cursor/hooks.json``, or ``None``."""
    hooks_json = project_root / ".cursor" / "hooks.json"
    if not hooks_json.exists():
        return None
    try:
        data = json.loads(hooks_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    hooks_obj = data.get("hooks")
    if not isinstance(hooks_obj, dict):
        return None
    session_entries = hooks_obj.get("sessionStart")
    if not isinstance(session_entries, list) or not session_entries:
        return None
    return session_entries


def _check_cursor_mcp_zombie_cleanup(project_root: Path) -> CheckResult | None:
    """Verify Cursor sessionStart does NOT run MCP zombie cleanup (deploy-local only)."""
    session_entries = _cursor_session_start_entries(project_root)
    if session_entries is None:
        return None
    zombie_cmds = {
        ".cursor/hooks/tapps-mcp-zombie-cleanup.sh",
        "powershell -NoProfile -ExecutionPolicy Bypass -File .cursor/hooks/tapps-mcp-zombie-cleanup.ps1",
    }
    stale = [
        e.get("command", "")
        for e in session_entries
        if isinstance(e, dict) and e.get("command", "") in zombie_cmds
    ]
    if stale:
        return CheckResult(
            "MCP zombie cleanup hook",
            False,
            "sessionStart must not run zombie cleanup — reap runs on deploy-local only",
            "Run: tapps-mcp upgrade --host cursor --force",
        )
    recall_cmd = ".cursor/hooks/tapps-memory-auto-recall.sh"
    has_recall = any(
        isinstance(e, dict) and e.get("command") == recall_cmd for e in session_entries
    )
    if not has_recall:
        return None
    return CheckResult(
        "MCP zombie cleanup hook",
        True,
        "sessionStart correctly omits zombie cleanup (reap on deploy-local)",
    )


def _parse_cursor_hooks_json(cursor_hooks_json: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    """Parse ``.cursor/hooks.json`` and return ``(data, format_errors, hook_warnings)``."""
    format_errors: list[str] = []
    hook_warnings: list[str] = []
    try:
        data = json.loads(cursor_hooks_json.read_text(encoding="utf-8"))
        if not isinstance(data.get("version"), (int, float)):
            format_errors.append("missing or non-numeric 'version' field")
        if isinstance(data.get("hooks"), list):
            format_errors.append("'hooks' is an array (should be an object)")
        elif not isinstance(data.get("hooks"), dict):
            format_errors.append("'hooks' is not an object")
        else:
            hooks_obj = data.get("hooks", {})
            unknown = [k for k in hooks_obj if k not in SUPPORTED_CURSOR_HOOK_KEYS]
            if unknown:
                hook_warnings.append(
                    "non-catalog hook keys (preserved by upgrade; verify against "
                    f"Cursor docs): {', '.join(sorted(unknown))}"
                )
    except (json.JSONDecodeError, OSError) as exc:
        format_errors.append(f"could not parse: {exc}")
        data = {}
    return data, format_errors, hook_warnings


def _windows_sh_hook_result(data: dict[str, Any]) -> CheckResult | None:
    """Flag ``.sh`` Cursor hook commands on Windows (they open in the editor, TROUBLESHOOTING.md)."""
    if sys.platform != "win32":
        return None
    hooks_obj = data.get("hooks", {})
    for entries in hooks_obj.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            cmd = entry.get("command", "")
            if "tapps-" in cmd and cmd.rstrip().endswith(".sh"):
                return CheckResult(
                    "Hooks",
                    False,
                    "On Windows, Cursor hooks are configured as .sh (Bash); "
                    "they open in the editor instead of running. Use PowerShell (.ps1) hooks.",
                    "Run: tapps-mcp upgrade --host cursor (or uv run tapps-mcp upgrade --host cursor)",
                )
    return None


def _check_cursor_hooks_config(
    project_root: Path,
    found: list[str],
) -> CheckResult | None:
    """Validate .cursor/hooks.json existence, format, and platform. Returns failure or None."""
    cursor_hooks_json = project_root / ".cursor" / "hooks.json"
    if not cursor_hooks_json.exists():
        return CheckResult(
            "Hooks",
            False,
            f"TappsMCP hooks found for: {', '.join(found)}, but .cursor/hooks.json missing",
            "Run: tapps-mcp upgrade --host cursor or upgrade --force",
        )

    data, format_errors, hook_warnings = _parse_cursor_hooks_json(cursor_hooks_json)

    if format_errors:
        return CheckResult(
            "Hooks",
            False,
            f"TappsMCP hooks found for: {', '.join(found)}, "
            f"but .cursor/hooks.json has invalid format: {'; '.join(format_errors)}",
            "Run: tapps-mcp upgrade --host cursor or upgrade --force to write only supported hooks",
        )

    if hook_warnings:
        return CheckResult(
            "Hooks",
            True,
            f"TappsMCP hooks found for: {', '.join(found)} ({'; '.join(hook_warnings)})",
        )

    zombie_result = _check_cursor_mcp_zombie_cleanup(project_root)
    if zombie_result is not None and not zombie_result.ok:
        return zombie_result

    return _windows_sh_hook_result(data)


def check_cursor_mcp_zombie_cleanup(project_root: Path) -> CheckResult:
    """Epic 109 / ADR-0005: sessionStart must not run zombie cleanup (deploy-local only)."""
    result = _check_cursor_mcp_zombie_cleanup(project_root)
    if result is not None:
        return result
    return CheckResult(
        "MCP zombie cleanup hook",
        True,
        "Not applicable (memory auto-recall not wired on sessionStart)",
    )


def _detect_hook_hosts(project_root: Path) -> tuple[list[str], list[str]]:
    """Return ``(hosts_with_tapps_hooks, hosts_missing_session_start_hook)``."""
    claude_hooks = project_root / ".claude" / "hooks"
    cursor_hooks = project_root / ".cursor" / "hooks"
    found: list[str] = []
    missing_session_start: list[str] = []

    if claude_hooks.is_dir() and any(claude_hooks.glob("tapps-*")):
        found.append("Claude Code")
        has_sh = (claude_hooks / "tapps-session-start.sh").exists()
        has_ps1 = (claude_hooks / "tapps-session-start.ps1").exists()
        if not has_sh and not has_ps1:
            missing_session_start.append("Claude Code")

    if cursor_hooks.is_dir() and any(cursor_hooks.glob("tapps-*")):
        found.append("Cursor")
        has_sh = (cursor_hooks / "tapps-before-mcp.sh").exists()
        has_ps1 = (cursor_hooks / "tapps-before-mcp.ps1").exists()
        if not has_sh and not has_ps1:
            missing_session_start.append("Cursor")

    return found, missing_session_start


def check_hooks(project_root: Path) -> CheckResult:
    """Check TappsMCP hooks: directory, session-start script, and config validity.

    For Claude Code, hook keys are validated in check_claude_settings.
    For Cursor, requires .cursor/hooks.json when scripts exist. Unknown hook
    event keys outside the catalog are reported as warnings (never stripped).
    """
    found, missing_session_start = _detect_hook_hosts(project_root)

    if not found:
        return CheckResult(
            "Hooks",
            False,
            "No TappsMCP hooks found",
            "Run: tapps-mcp upgrade",
        )

    if missing_session_start:
        return CheckResult(
            "Hooks",
            False,
            f"TappsMCP hooks found for: {', '.join(found)}, "
            f"but session-start hook missing for: {', '.join(missing_session_start)}",
            "Run: tapps-mcp upgrade --force (or upgrade --host cursor)",
        )

    zombie_note = ""
    if "Cursor" in found:
        cursor_result = _check_cursor_hooks_config(project_root, found)
        if cursor_result is not None:
            return cursor_result
        zombie_result = _check_cursor_mcp_zombie_cleanup(project_root)
        if zombie_result is not None and zombie_result.ok:
            zombie_note = "; MCP zombie reap on deploy-local (not sessionStart)"

    return CheckResult(
        "Hooks",
        True,
        f"TappsMCP hooks found for: {', '.join(found)} (including session-start){zombie_note}",
    )
