"""NLT MCP plugin server and bundle definitions (Epic 109).

Canonical spec: ``docs/architecture/nlt-mcp-plugin-spec.yaml``.
"""

from __future__ import annotations

from typing import Any, Final, Literal

NltBundle = Literal["developer", "planning", "docs", "release"]

NLT_SERVER_ORDER: Final[tuple[str, ...]] = (
    "nlt-code-quality",
    "nlt-platform-admin",
    "nlt-linear-issues",
    "nlt-project-docs",
    "nlt-release-ship",
)

NLT_SERVER_SPECS: Final[dict[str, dict[str, Any]]] = {
    "nlt-code-quality": {
        "display_name": "Code Quality",
        "tagline": "Score, gate, and secure code while you edit.",
        "serve_command": "tapps-mcp",
        "serve_args": ["serve", "--profile", "nlt-code-quality"],
        "env_kind": "tapps",
    },
    "nlt-platform-admin": {
        "display_name": "Platform Admin",
        "tagline": "Bootstrap, upgrade, diagnose, and observe TappsMCP in your project.",
        "serve_command": "tapps-mcp",
        "serve_args": ["serve", "--profile", "nlt-platform-admin"],
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
    "developer": ("nlt-code-quality", "nlt-platform-admin"),
    "planning": ("nlt-code-quality", "nlt-platform-admin", "nlt-linear-issues"),
    "docs": ("nlt-code-quality", "nlt-platform-admin", "nlt-project-docs"),
    "release": ("nlt-code-quality", "nlt-platform-admin", "nlt-release-ship"),
}

# Eager / total tool counts per spec (Epic 109.5 doctor thresholds).
NLT_SERVER_EAGER_COUNTS: Final[dict[str, int]] = {
    "nlt-code-quality": 9,
    "nlt-platform-admin": 2,
    "nlt-linear-issues": 7,
    "nlt-project-docs": 6,
    "nlt-release-ship": 5,
}
NLT_SERVER_TOTAL_COUNTS: Final[dict[str, int]] = {
    "nlt-code-quality": 15,
    "nlt-platform-admin": 14,
    "nlt-linear-issues": 15,
    "nlt-project-docs": 27,
    "nlt-release-ship": 7,
}
NLT_MAX_ENABLED_SERVERS: Final[int] = 3
NLT_MAX_COMBINED_EAGER: Final[int] = 20

_LEGACY_MCP_SERVER_IDS: Final[frozenset[str]] = frozenset({"tapps-mcp", "docs-mcp"})


def normalize_mcp_bundle(bundle: str | None) -> NltBundle:
    """Return a valid bundle name; default ``developer`` (never ``full``)."""
    if bundle in NLT_BUNDLES:
        return bundle  # type: ignore[return-value]
    return "developer"


def enabled_servers_for_bundle(bundle: NltBundle) -> tuple[str, ...]:
    """Servers written as active MCP entries for *bundle*."""
    return NLT_BUNDLES[bundle]


def commented_servers_for_bundle(bundle: NltBundle) -> tuple[str, ...]:
    """Servers emitted as commented opt-in blocks for *bundle*."""
    enabled = set(enabled_servers_for_bundle(bundle))
    return tuple(sid for sid in NLT_SERVER_ORDER if sid not in enabled)


def is_nlt_server_id(server_id: str) -> bool:
    return server_id in NLT_SERVER_SPECS


def list_nlt_server_ids_in_config(servers: dict[str, Any]) -> list[str]:
    """Return enabled ``nlt-*`` server IDs present in an MCP servers dict."""
    return [sid for sid in NLT_SERVER_ORDER if sid in servers and isinstance(servers[sid], dict)]


def nlt_eager_count(server_id: str) -> int | None:
    """Return the spec eager-tool count for an NLT server ID."""
    return NLT_SERVER_EAGER_COUNTS.get(server_id)


def nlt_total_tool_count(server_id: str) -> int | None:
    """Return the spec total-tool count for an NLT server ID."""
    return NLT_SERVER_TOTAL_COUNTS.get(server_id)
