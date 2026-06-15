"""NLT MCP plugin server and bundle definitions (Epic 109, ADR-0016).

Canonical spec: ``docs/architecture/nlt-mcp-plugin-spec.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final, Literal

NltBundle = Literal[
    "developer",
    "minimal",
    "memory",
    "planning",
    "docs",
    "release",
    "security",
    "audit",
    "full",
]

NLT_SERVER_ORDER: Final[tuple[str, ...]] = (
    "nlt-build",
    "nlt-memory",
    "nlt-setup",
    "nlt-linear-issues",
    "nlt-project-docs",
    "nlt-release-ship",
)

# One-release migration from Epic 109 server IDs (ADR-0016).
LEGACY_NLT_SERVER_IDS: Final[dict[str, str]] = {
    "nlt-code-quality": "nlt-build",
    "nlt-platform-admin": "nlt-setup",
}

NLT_SERVER_SPECS: Final[dict[str, dict[str, Any]]] = {
    "nlt-build": {
        "display_name": "Build",
        "tagline": "Score, gate, and secure code while you edit.",
        "serve_command": "tapps-mcp",
        "serve_args": ["serve", "--profile", "nlt-build"],
        "env_kind": "tapps",
    },
    "nlt-memory": {
        "display_name": "Memory",
        "tagline": "Recall, save, and session continuity via tapps-brain.",
        "serve_command": "tapps-mcp",
        "serve_args": ["serve", "--profile", "nlt-memory"],
        "env_kind": "tapps",
    },
    "nlt-setup": {
        "display_name": "Setup",
        "tagline": "Bootstrap, upgrade, diagnose, and observe TappsMCP in your project.",
        "serve_command": "tapps-mcp",
        "serve_args": ["serve", "--profile", "nlt-setup"],
        "env_kind": "tapps",
    },
    "nlt-linear-issues": {
        "display_name": "Linear Issues",
        "tagline": "Create, lint, validate, and triage agent-ready Linear issues.",
        "serve_command": "tapps-platform",
        "serve_args": ["serve", "--profile", "nlt-linear-issues"],
        "env_kind": "tapps",
    },
    "nlt-project-docs": {
        "display_name": "Project Docs",
        "tagline": "Generate and audit project documentation from the codebase.",
        "serve_command": "docsmcp",
        "serve_args": ["serve", "--profile", "nlt-project-docs"],
        "env_kind": "docs",
    },
    "nlt-release-ship": {
        "display_name": "Release & Ship",
        "tagline": "Changelog, release notes, release gates, and pre-ship CVE checks.",
        "serve_command": "tapps-platform",
        "serve_args": ["serve", "--profile", "nlt-release-ship"],
        "env_kind": "tapps",
    },
}

NLT_BUNDLES: Final[dict[NltBundle, tuple[str, ...]]] = {
    "developer": ("nlt-build", "nlt-memory", "nlt-linear-issues"),
    "minimal": ("nlt-build",),
    "memory": ("nlt-build", "nlt-memory"),
    "planning": ("nlt-build", "nlt-linear-issues"),
    "docs": ("nlt-build", "nlt-project-docs"),
    "release": ("nlt-build", "nlt-release-ship"),
    "security": ("nlt-build",),
    "audit": ("nlt-build", "nlt-linear-issues"),
    "full": NLT_SERVER_ORDER,
}

# Eager / total tool counts per spec (Epic 109.5 / ADR-0016 doctor thresholds).
NLT_SERVER_EAGER_COUNTS: Final[dict[str, int]] = {
    "nlt-build": 9,
    "nlt-memory": 2,
    "nlt-setup": 2,
    "nlt-linear-issues": 7,
    "nlt-project-docs": 6,
    "nlt-release-ship": 5,
    # Legacy profile names in --profile args map to same counts
    "nlt-code-quality": 9,
    "nlt-platform-admin": 2,
}

NLT_SERVER_TOTAL_COUNTS: Final[dict[str, int]] = {
    "nlt-build": 16,
    "nlt-memory": 4,
    "nlt-setup": 7,
    "nlt-linear-issues": 15,
    "nlt-project-docs": 27,
    "nlt-release-ship": 6,
    "nlt-code-quality": 16,
    "nlt-platform-admin": 7,
}

NLT_MAX_ENABLED_SERVERS: Final[int] = 3
NLT_MAX_COMBINED_EAGER: Final[int] = 20

_LEGACY_MCP_SERVER_IDS: Final[frozenset[str]] = frozenset({
    "tapps-mcp",
    "docs-mcp",
    "nlt-code-quality",
    "nlt-platform-admin",
})

# Tool → owning NLT server (for server-aware checklist — TAP-3899).
NLT_TOOL_SERVER: Final[dict[str, str]] = {
    "tapps_session_start": "nlt-build",
    "tapps_quick_check": "nlt-build",
    "tapps_validate_changed": "nlt-build",
    "tapps_quality_gate": "nlt-build",
    "tapps_checklist": "nlt-build",
    "tapps_lookup_docs": "nlt-build",
    "tapps_score_file": "nlt-build",
    "tapps_security_scan": "nlt-build",
    "tapps_impact_analysis": "nlt-build",
    "tapps_usage": "nlt-build",
    "tapps_validate_config": "nlt-build",
    "tapps_dead_code": "nlt-build",
    "tapps_dependency_graph": "nlt-build",
    "tapps_dependency_scan": "nlt-build",
    "tapps_report": "nlt-build",
    "tapps_audit_campaign": "nlt-build",
    "tapps_memory": "nlt-memory",
    "tapps_session_notes": "nlt-memory",
    "tapps_session_end": "nlt-memory",
    "tapps_handoff_save": "nlt-memory",
    "tapps_init": "nlt-setup",
    "tapps_upgrade": "nlt-setup",
    "tapps_doctor": "nlt-setup",
    "tapps_server_info": "nlt-setup",
    "tapps_set_engagement_level": "nlt-setup",
    "tapps_pipeline": "nlt-setup",
    "tapps_stats": "nlt-setup",
    "tapps_release_update": "nlt-release-ship",
    "tapps_finding_to_story": "nlt-linear-issues",
    "tapps_audit_close_coverage": "nlt-linear-issues",
    "tapps_linear_snapshot_get": "nlt-linear-issues",
    "tapps_linear_snapshot_put": "nlt-linear-issues",
    "tapps_linear_snapshot_invalidate": "nlt-linear-issues",
    "tapps_linear_count": "nlt-linear-issues",
    "tapps_linear_list_issues": "nlt-linear-issues",
}


def normalize_mcp_bundle(bundle: str | None) -> NltBundle:
    """Return a valid bundle name; default ``developer`` (never ``full``)."""
    if bundle in NLT_BUNDLES:
        return bundle  # type: ignore[return-value]
    return "developer"


def enabled_servers_for_bundle(bundle: NltBundle) -> tuple[str, ...]:
    """Recommended servers for a task bundle (doctor hints, session guidance)."""
    return NLT_BUNDLES[bundle]


def mcp_config_servers_for_bundle(bundle: NltBundle) -> tuple[str, ...]:
    """Servers written as active MCP entries for host config files.

    All six ``nlt-*`` servers are emitted so Cursor/VS Code users can toggle
    them in the MCP UI. *bundle* selects the recommended subset for messaging
    only — not which entries appear in ``mcp.json``.
    """
    _ = bundle
    return NLT_SERVER_ORDER


def commented_servers_for_bundle(bundle: NltBundle) -> tuple[str, ...]:
    """No commented opt-in blocks — every server is a real toggleable entry."""
    _ = bundle
    return ()


def is_nlt_server_id(server_id: str) -> bool:
    return server_id in NLT_SERVER_SPECS or server_id in LEGACY_NLT_SERVER_IDS


def canonical_nlt_server_id(server_id: str) -> str:
    """Map legacy Epic 109 server IDs to ADR-0016 IDs."""
    return LEGACY_NLT_SERVER_IDS.get(server_id, server_id)


def list_nlt_server_ids_in_config(servers: dict[str, Any]) -> list[str]:
    """Return enabled ``nlt-*`` server IDs present in an MCP servers dict."""
    found: list[str] = []
    for sid in servers:
        if not isinstance(servers.get(sid), dict):
            continue
        canonical = canonical_nlt_server_id(sid)
        if canonical in NLT_SERVER_ORDER and canonical not in found:
            found.append(canonical)
    return found


def needs_legacy_nlt_migration(servers: dict[str, Any]) -> bool:
    """Return True when legacy monolith entries exist but no ``nlt-*`` servers."""
    if not isinstance(servers, dict):
        return False
    has_legacy = bool(_LEGACY_MCP_SERVER_IDS & set(servers.keys()))
    has_nlt = bool(list_nlt_server_ids_in_config(servers))
    return has_legacy and not has_nlt


def nlt_eager_count(server_id: str) -> int | None:
    """Return the spec eager-tool count for an NLT server ID."""
    canonical = canonical_nlt_server_id(server_id)
    return NLT_SERVER_EAGER_COUNTS.get(canonical) or NLT_SERVER_EAGER_COUNTS.get(server_id)


def nlt_total_tool_count(server_id: str) -> int | None:
    """Return the spec total-tool count for an NLT server ID."""
    canonical = canonical_nlt_server_id(server_id)
    return NLT_SERVER_TOTAL_COUNTS.get(canonical) or NLT_SERVER_TOTAL_COUNTS.get(server_id)


def _load_enabled_mcp_servers(project_root: Path) -> dict[str, Any]:
    """Merge enabled MCP server entries from project host configs."""
    from tapps_mcp.distribution.setup_generator import (
        _get_config_path,
        _get_servers_key,
        _load_mcp_config_json,
    )

    merged: dict[str, Any] = {}
    for host in ("claude-code", "cursor", "vscode"):
        path = _get_config_path(host, project_root)
        if not path.exists():
            continue
        data = _load_mcp_config_json(path)
        servers_key = _get_servers_key(host)
        servers = data.get(servers_key)
        if not isinstance(servers, dict):
            continue
        for name, entry in servers.items():
            if isinstance(entry, dict):
                merged[str(name)] = entry
    return merged


def tools_on_enabled_nlt_servers(project_root: Path | None) -> frozenset[str]:
    """Union of tapps tool names available on enabled NLT servers in MCP config."""
    if project_root is None:
        return frozenset(NLT_TOOL_SERVER.keys())

    try:
        servers = _load_enabled_mcp_servers(project_root)
    except Exception:
        return frozenset(NLT_TOOL_SERVER.keys())

    enabled_ids = set(list_nlt_server_ids_in_config(servers))
    if not enabled_ids:
        enabled_ids = {"nlt-build"}

    available: set[str] = set()
    for tool, owner in NLT_TOOL_SERVER.items():
        if owner in enabled_ids:
            available.add(tool)
    return frozenset(available)


def tool_unavailable_reason(tool_name: str, enabled_servers: frozenset[str]) -> str | None:
    """Return a hint when *tool_name* requires a disabled NLT server."""
    owner = NLT_TOOL_SERVER.get(tool_name)
    if owner is None or owner in enabled_servers:
        return None
    return f"Enable `{owner}` MCP server (or use CLI fallback) for `{tool_name}`"
