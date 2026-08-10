"""Claude Code permission entries and ``.claude/settings.json`` bootstrap.

Split out of :mod:`~tapps_mcp.pipeline.init` (TAP-5733); the names here are
re-exported from that module so existing call sites keep working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

# Both entries needed for Claude Code permissions: bare match is the reliable
# fallback (issue #3107), wildcard is the official syntax from v2.0.70+.
_CLAUDE_PERMISSION_ENTRIES = ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]

# Epic 109 NLT plugin servers (added alongside legacy entries for one release).
_NLT_PERMISSION_ENTRIES = [
    "mcp__nlt-build",
    "mcp__nlt-build__*",
    "mcp__nlt-memory",
    "mcp__nlt-memory__*",
    "mcp__nlt-setup",
    "mcp__nlt-setup__*",
    "mcp__nlt-code-quality",
    "mcp__nlt-code-quality__*",
    "mcp__nlt-platform-admin",
    "mcp__nlt-platform-admin__*",
    "mcp__nlt-linear-issues",
    "mcp__nlt-linear-issues__*",
    "mcp__nlt-project-docs",
    "mcp__nlt-project-docs__*",
    "mcp__nlt-release-ship",
    "mcp__nlt-release-ship__*",
]

# DocsMCP permission entries — added when DocsMCP is detected.
_DOCSMCP_PERMISSION_ENTRIES = ["mcp__docs-mcp", "mcp__docs-mcp__*"]

# TappsPlatform (combined server) permission entries — added when DocsMCP is detected.
_PLATFORM_PERMISSION_ENTRIES = ["mcp__tapps-platform", "mcp__tapps-platform__*"]

# Extra permissions granted at high engagement level so the LLM can
# auto-run quality checkers without user confirmation.
_CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS = [
    "Bash(uv run ruff *)",
    "Bash(uv run mypy *)",
]

_CLAUDE_DENY_RULES: list[str] = [
    "Bash(rm -rf *)",
    "Bash(git push --force *)",
    "Bash(git reset --hard *)",
    "Read(.env)",
    "Read(.env.*)",
]

_CLAUDE_SETTINGS_SCHEMA = "https://json.schemastore.org/claude-code-settings.json"


def generate_permission_settings(
    project_root: Path,
    engagement_level: str = "medium",
    existing_settings: dict[str, Any] | None = None,
    *,
    docsmcp_detected: bool = False,
    use_nlt_plugin: bool = True,
) -> dict[str, Any]:
    """Generate ``.claude/settings.json`` content with permission rules.

    Builds the base MCP permission entries and, at ``high`` engagement,
    appends extra ``Bash(...)`` entries so the LLM can auto-run checkers.

    Merges into *existing_settings* when provided (preserving all user
    keys and deduplicating the ``permissions.allow`` list).

    Args:
        project_root: Target project root (unused today but reserved
            for future per-project customisation).
        engagement_level: ``"high"``, ``"medium"`` (default), or ``"low"``.
        existing_settings: Parsed contents of an existing ``settings.json``.
            ``None`` starts from an empty dict.
        docsmcp_detected: When True, include DocsMCP permission entries (legacy monolith).
        use_nlt_plugin: When True (default), include Epic 109 ``nlt-*`` server entries.

    Returns:
        The merged settings dict ready to be serialised to JSON.
    """
    import copy

    config: dict[str, Any] = copy.deepcopy(existing_settings) if existing_settings else {}

    # 2026 best practice: JSON schema reference
    config.setdefault("$schema", _CLAUDE_SETTINGS_SCHEMA)

    # 2026 best practice: enable project MCP servers
    config.setdefault("enableAllProjectMcpServers", True)

    # 2026 best practice: agent teams at high engagement
    if engagement_level == "high":
        env: dict[str, str] = config.setdefault("env", {})
        env.setdefault("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")

    # Permissions: allow list
    permissions: dict[str, Any] = config.setdefault("permissions", {})
    allow_list: list[str] = permissions.setdefault("allow", [])

    desired: list[str] = list(_CLAUDE_PERMISSION_ENTRIES)
    if use_nlt_plugin:
        desired.extend(_NLT_PERMISSION_ENTRIES)
    if docsmcp_detected and not use_nlt_plugin:
        desired.extend(_DOCSMCP_PERMISSION_ENTRIES)
        desired.extend(_PLATFORM_PERMISSION_ENTRIES)
    if engagement_level == "high":
        desired.extend(_CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS)

    for entry in desired:
        if entry not in allow_list:
            allow_list.append(entry)

    # Permissions: deny list (safety guardrails)
    deny_list: list[str] = permissions.setdefault("deny", [])
    for entry in _CLAUDE_DENY_RULES:
        if entry not in deny_list:
            deny_list.append(entry)

    return config


def _bootstrap_claude_settings(
    project_root: Path,
    engagement_level: str = "medium",
    *,
    docsmcp_detected: bool = False,
    use_nlt_plugin: bool = True,
) -> str:
    """Create or update ``.claude/settings.json`` with permission entries.

    Adds **both** ``"mcp__tapps-mcp"`` (bare server match - confirmed
    working in Claude Code issue #3107) and ``"mcp__tapps-mcp__*"``
    (wildcard match - added in Claude Code 2.0.70) to ``permissions.allow``.
    Using both syntaxes works around a known Claude Code bug where the
    wildcard variant is sometimes not honoured (issues #13077, #14730,
    #27139).

    At ``high`` engagement, also adds ``Bash(uv run ruff *)`` and
    ``Bash(uv run mypy *)`` so the LLM can auto-run quality checkers.

    When *docsmcp_detected* is True, also adds DocsMCP permission entries.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    import json
    from pathlib import Path as _Path

    settings_dir = _Path(project_root) / ".claude"
    settings_file = settings_dir / "settings.json"

    if not settings_file.exists():
        settings_dir.mkdir(parents=True, exist_ok=True)
        config = generate_permission_settings(
            project_root,
            engagement_level=engagement_level,
            docsmcp_detected=docsmcp_detected,
            use_nlt_plugin=use_nlt_plugin,
        )
        from tapps_mcp.pipeline.platform_hooks import _write_managed_json

        _write_managed_json(settings_file, config)
        return "created"

    raw = settings_file.read_text(encoding="utf-8")
    try:
        existing: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # Malformed JSON — leave the file untouched rather than corrupting it.
        return "skipped"

    merged = generate_permission_settings(
        project_root,
        engagement_level=engagement_level,
        existing_settings=existing,
        docsmcp_detected=docsmcp_detected,
        use_nlt_plugin=use_nlt_plugin,
    )

    if merged == existing:
        return "skipped"

    from tapps_mcp.pipeline.platform_hooks import _write_managed_json

    _write_managed_json(settings_file, merged)
    return "updated"
