"""NLT cross-package tool profiles for ``tapps-platform serve --profile``.

Canonical spec: ``docs/architecture/nlt-mcp-plugin-spec.yaml`` servers
``nlt-linear-issues`` and ``nlt-release-ship``.
"""

from __future__ import annotations

from typing import Final

TOOL_PROFILE_NLT_LINEAR_ISSUES: Final[frozenset[str]] = frozenset(
    {
        "docs_generate_epic",
        "docs_generate_story",
        "docs_lint_linear_issue",
        "docs_validate_linear_issue",
        "docs_save_linear_issue",
        "docs_generate_prompt",
        "docs_linear_triage",
        "docs_validate_epic",
        "tapps_linear_snapshot_get",
        "tapps_finding_to_story",
        "tapps_linear_snapshot_put",
        "tapps_linear_snapshot_invalidate",
        "tapps_linear_count",
        "tapps_linear_list_issues",
        "tapps_audit_close_coverage",
    }
)

TOOL_PROFILE_NLT_RELEASE_SHIP: Final[frozenset[str]] = frozenset(
    {
        "docs_generate_changelog",
        "docs_generate_release_update",
        "docs_validate_release_update",
        "docs_release_gate",
        "docs_generate_release_notes",
        "tapps_release_update",
    }
)

PLATFORM_NLT_PROFILES: Final[dict[str, frozenset[str]]] = {
    "nlt-linear-issues": TOOL_PROFILE_NLT_LINEAR_ISSUES,
    "nlt-release-ship": TOOL_PROFILE_NLT_RELEASE_SHIP,
}

# TAP-6062: the tool surface an out-of-process agent runtime (AgentForge) may
# reach with a fleet *runtime* bearer token. Deliberately far narrower than
# ``nlt-build``'s registered profile: read-only lookups plus the two scanners,
# nothing that writes a file, bootstraps a session, or touches Linear/memory.
# Enforced server-side per request on both ``tools/list`` and ``tools/call``
# (see :mod:`tapps_mcp.http_fleet_scope`) -- the client's advertised list is
# never the gate.
TOOL_PROFILE_FLEET_RUNTIME: Final[frozenset[str]] = frozenset(
    {
        "tapps_lookup_docs",
        "tapps_research",
        "tapps_security_scan",
        "tapps_dependency_scan",
    }
)

#: Fleet server ids that accept the runtime token type at all.
RUNTIME_SCOPE_SERVERS: Final[frozenset[str]] = frozenset({"nlt-build"})

FLEET_SCOPE_PROFILES: Final[dict[str, frozenset[str]]] = {
    "runtime": TOOL_PROFILE_FLEET_RUNTIME,
}


def resolve_fleet_scope_tools(scope: str | None) -> frozenset[str] | None:
    """Return the allowlist for a fleet auth *scope*, or ``None`` when unscoped.

    ``None`` means "no per-request narrowing" -- an operator-scoped request, or
    a stdio call. Any scope we do not recognise is treated as unscoped by this
    resolver; the auth layer has already refused unknown credentials.
    """
    if scope is None:
        return None
    return FLEET_SCOPE_PROFILES.get(scope)


def resolve_platform_allowed_tools(profile: str | None) -> frozenset[str] | None:
    """Return allowed tool names for *profile*, or ``None`` for full combined mode."""
    if profile is None:
        return None
    if profile not in PLATFORM_NLT_PROFILES:
        msg = f"Unknown tapps-platform profile: {profile!r}"
        raise ValueError(msg)
    return PLATFORM_NLT_PROFILES[profile]
