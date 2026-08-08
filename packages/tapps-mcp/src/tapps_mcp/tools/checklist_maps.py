"""Task-type to tool-name maps for ``tapps_checklist``.

One map per engagement level (high / medium / low), plus the short reasons
surfaced as checklist hints. Split out of ``checklist.py`` — these are data,
and they dominated that module's line count.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Short reasons for checklist hints (so the LLM knows what to do)
# ---------------------------------------------------------------------------

TOOL_REASONS: dict[str, str] = {
    "tapps_server_info": "Call at session start to discover server version and installed checkers.",
    "tapps_session_start": (
        "Call as the FIRST action in every session to discover server version, installed checkers, and project context."
    ),
    "tapps_session_end": (
        "Call at session end to process session events through the brain flywheel and close the feedback loop."
    ),
    "tapps_score_file": (
        "Score the file for quality; use quick=True during edits, full before done."
    ),
    "tapps_security_scan": "Run a dedicated security scan (bandit + secrets) on the file.",
    "tapps_quality_gate": (
        "Call before declaring work complete to ensure the file passes the quality preset."
    ),
    "tapps_lookup_docs": "Look up library docs before using an API to avoid hallucinated usage.",
    "tapps_research": (
        "Unified research front door (ADR-0030): library/API → lookup_docs; "
        "open-ended/latest → brain web_research; URL scrape → research_fetch."
    ),
    "tapps_validate_config": (
        "Validate Dockerfile, docker-compose, MCP server configs (.mcp.json), "
        "YAML manifests (config_type=yaml_manifest), or other infra config "
        "against best practices."
    ),
    "tapps_checklist": (
        "Call before declaring work complete to verify no required steps were skipped."
    ),
    "tapps_validate_changed": (
        "Batch-validate changed files (score + gate + optional blocking judges). "
        "For document/PDF work use task_type=document and configure validate_changed.judges."
    ),
    "tapps_quick_check": (
        "Quick score + gate + security in one call. Minimum check after editing any Python file."
    ),
    "tapps_dead_code": (
        "Scan for unused functions, classes, imports, and variables. Use during refactoring."
    ),
    "tapps_dependency_scan": (
        "Scan dependencies for known vulnerabilities (CVEs). Use before releases."
    ),
    "tapps_dependency_graph": (
        "Analyze import graph for circular dependencies and coupling. Use before major refactoring."
    ),
    "tapps_set_engagement_level": (
        "When the user requests to change enforcement intensity"
        " (e.g. 'set tappsmcp to high' or 'make checks optional')."
    ),
    "tapps_decompose": (
        "Decompose a task into ~15-minute units with model tier hints before starting work."
    ),
    "tapps_release_update": (
        "Generate and validate a release update document body from CHANGELOG or git log."
        " Call before posting a version release to Linear via the linear-release-update skill."
    ),
    "tapps_impact_analysis": ("Map module-level import blast radius before API or layout changes."),
    "tapps_call_graph": ("Query function-level callers/callees before changing a specific symbol."),
    "tapps_diff_impact": (
        "Rank affected tests for a set of changed Python files before declaring done."
    ),
    "tapps_audit_close_coverage": (
        "Close an audit finding's brain coverage after a fix lands — updates the file's"
        " audited SHA and links the fix/finding tickets. Call after committing an audit fix."
    ),
}


# ---------------------------------------------------------------------------
# Recommended tool sets per task type (medium = default)
# ---------------------------------------------------------------------------

TASK_TOOL_MAP: dict[str, dict[str, list[str]]] = {
    "feature": {
        "required": ["tapps_score_file", "tapps_quality_gate"],
        "recommended": ["tapps_security_scan"],
        "optional": ["tapps_checklist"],
    },
    "bugfix": {
        "required": ["tapps_score_file"],
        "recommended": ["tapps_quality_gate", "tapps_security_scan"],
        "optional": ["tapps_checklist"],
    },
    "refactor": {
        "required": ["tapps_score_file", "tapps_quality_gate"],
        "recommended": [
            "tapps_dead_code",
            "tapps_dependency_graph",
            "tapps_impact_analysis",
            "tapps_call_graph",
            "tapps_diff_impact",
        ],
        "optional": ["tapps_security_scan", "tapps_checklist"],
    },
    "security": {
        "required": ["tapps_security_scan", "tapps_quality_gate"],
        "recommended": ["tapps_score_file", "tapps_dependency_scan"],
        "optional": ["tapps_checklist"],
    },
    "review": {
        "required": ["tapps_score_file", "tapps_security_scan", "tapps_quality_gate"],
        "recommended": ["tapps_checklist", "tapps_dead_code"],
        "optional": [
            "tapps_dependency_scan",
            "tapps_dependency_graph",
            "tapps_audit_campaign",
            "tapps_audit_close_coverage",
        ],
    },
    "epic": {
        "required": ["tapps_checklist"],
        "recommended": ["tapps_score_file", "tapps_quality_gate"],
        "optional": ["tapps_security_scan", "tapps_validate_changed"],
    },
    "release": {
        "required": ["tapps_release_update"],
        "recommended": ["tapps_dependency_scan"],
        "optional": ["tapps_checklist"],
    },
    "document": {
        "required": ["tapps_validate_changed"],
        "recommended": ["tapps_validate_config", "tapps_lookup_docs", "tapps_checklist"],
        "optional": ["tapps_impact_analysis"],
    },
    "documentation": {
        "required": [],
        "recommended": ["tapps_checklist"],
        "optional": ["tapps_lookup_docs"],
    },
    "qa": {
        "required": ["tapps_validate_changed", "tapps_security_scan", "tapps_quality_gate"],
        "recommended": ["tapps_diff_impact", "tapps_checklist"],
        "optional": ["tapps_score_file"],
    },
    "frontend": {
        "required": ["tapps_lookup_docs", "tapps_quality_gate"],
        "recommended": ["tapps_score_file", "tapps_validate_changed", "tapps_checklist"],
        "optional": ["tapps_quick_check"],
    },
}

# High engagement: more tools required (stricter)
TASK_TOOL_MAP_HIGH: dict[str, dict[str, list[str]]] = {
    "feature": {
        "required": ["tapps_score_file", "tapps_quality_gate", "tapps_security_scan"],
        "recommended": ["tapps_validate_changed", "tapps_checklist"],
        "optional": [],
    },
    "bugfix": {
        "required": ["tapps_score_file", "tapps_quality_gate"],
        "recommended": ["tapps_security_scan", "tapps_checklist"],
        "optional": [],
    },
    "refactor": {
        "required": ["tapps_score_file", "tapps_quality_gate", "tapps_dead_code"],
        "recommended": [
            "tapps_dependency_graph",
            "tapps_impact_analysis",
            "tapps_call_graph",
            "tapps_diff_impact",
            "tapps_security_scan",
            "tapps_checklist",
        ],
        "optional": [],
    },
    "security": {
        "required": ["tapps_security_scan", "tapps_quality_gate", "tapps_score_file"],
        "recommended": ["tapps_dependency_scan", "tapps_checklist"],
        "optional": [],
    },
    "review": {
        "required": [
            "tapps_score_file",
            "tapps_security_scan",
            "tapps_quality_gate",
            "tapps_checklist",
        ],
        "recommended": ["tapps_dead_code", "tapps_validate_changed"],
        "optional": [
            "tapps_dependency_scan",
            "tapps_dependency_graph",
            "tapps_audit_campaign",
            "tapps_audit_close_coverage",
        ],
    },
    "epic": {
        "required": ["tapps_checklist", "tapps_score_file"],
        "recommended": ["tapps_quality_gate", "tapps_validate_changed"],
        "optional": ["tapps_security_scan"],
    },
    "release": {
        "required": ["tapps_release_update", "tapps_dependency_scan"],
        "recommended": ["tapps_checklist", "tapps_security_scan"],
        "optional": [],
    },
    "document": {
        "required": ["tapps_validate_changed", "tapps_checklist"],
        "recommended": ["tapps_validate_config", "tapps_lookup_docs", "tapps_quality_gate"],
        "optional": ["tapps_impact_analysis"],
    },
    "documentation": {
        "required": ["tapps_checklist"],
        "recommended": [],
        "optional": ["tapps_lookup_docs"],
    },
    "qa": {
        "required": [
            "tapps_validate_changed",
            "tapps_security_scan",
            "tapps_quality_gate",
            "tapps_checklist",
        ],
        "recommended": ["tapps_diff_impact", "tapps_score_file"],
        "optional": [],
    },
    "frontend": {
        "required": ["tapps_lookup_docs", "tapps_quality_gate", "tapps_validate_changed"],
        "recommended": ["tapps_score_file", "tapps_checklist"],
        "optional": ["tapps_quick_check"],
    },
}

# Low engagement: fewer tools required (lighter)
TASK_TOOL_MAP_LOW: dict[str, dict[str, list[str]]] = {
    "feature": {
        "required": ["tapps_quality_gate"],
        "recommended": ["tapps_score_file", "tapps_quick_check"],
        "optional": ["tapps_security_scan", "tapps_checklist"],
    },
    "bugfix": {
        "required": [],
        "recommended": ["tapps_score_file", "tapps_quality_gate"],
        "optional": ["tapps_security_scan", "tapps_checklist"],
    },
    "refactor": {
        "required": ["tapps_quality_gate"],
        "recommended": ["tapps_score_file", "tapps_dead_code"],
        "optional": ["tapps_dependency_graph", "tapps_security_scan", "tapps_checklist"],
    },
    "security": {
        "required": ["tapps_security_scan", "tapps_quality_gate"],
        "recommended": ["tapps_score_file"],
        "optional": ["tapps_dependency_scan", "tapps_checklist"],
    },
    "review": {
        "required": ["tapps_quality_gate"],
        "recommended": ["tapps_score_file", "tapps_security_scan", "tapps_checklist"],
        "optional": ["tapps_dead_code", "tapps_dependency_scan", "tapps_dependency_graph"],
    },
    "epic": {
        "required": ["tapps_checklist"],
        "recommended": ["tapps_score_file"],
        "optional": ["tapps_quality_gate", "tapps_validate_changed"],
    },
    "release": {
        "required": ["tapps_release_update"],
        "recommended": ["tapps_dependency_scan"],
        "optional": ["tapps_checklist"],
    },
    "document": {
        "required": ["tapps_validate_changed"],
        "recommended": ["tapps_validate_config", "tapps_lookup_docs"],
        "optional": ["tapps_checklist", "tapps_impact_analysis"],
    },
    "documentation": {
        "required": [],
        "recommended": [],
        "optional": ["tapps_checklist", "tapps_lookup_docs"],
    },
    "qa": {
        "required": ["tapps_quality_gate", "tapps_security_scan"],
        "recommended": ["tapps_validate_changed", "tapps_checklist"],
        "optional": ["tapps_diff_impact"],
    },
    "frontend": {
        "required": ["tapps_lookup_docs"],
        "recommended": ["tapps_quality_gate", "tapps_quick_check"],
        "optional": ["tapps_checklist"],
    },
}

# Alias for medium (same as TASK_TOOL_MAP)
TASK_TOOL_MAP_MEDIUM: dict[str, dict[str, list[str]]] = TASK_TOOL_MAP

_ENGAGEMENT_TOOL_MAP: dict[str, dict[str, dict[str, list[str]]]] = {
    "high": TASK_TOOL_MAP_HIGH,
    "medium": TASK_TOOL_MAP_MEDIUM,
    "low": TASK_TOOL_MAP_LOW,
}

KNOWN_TASK_TYPES: frozenset[str] = frozenset(TASK_TOOL_MAP.keys())

TASK_TYPE_REASONS: dict[str, str] = {
    "document": (
        "Document/PDF/HTML output work: run validate_changed with blocking judges "
        "(shell/pytest audit CLIs), validate_config for brand/template YAML manifests, "
        "and rebuild shipped outputs after layout changes."
    ),
    "documentation": (
        "Project documentation work: invoke /tapps-docs-bootstrap or /tapps-docs-refresh "
        "skills (nlt-project-docs). Finish with /tapps-docs-finish-task for drift, links, "
        "and completeness checks."
    ),
    "qa": (
        "QA and test-validation work: use /tapps-domain-testing or task_type=qa; "
        "require validate_changed, security_scan, and diff_impact when tests are in scope."
    ),
    "frontend": (
        "Frontend/UX work: use /tapps-domain-frontend or /tapps-flow-frontend; "
        "lookup_docs for UI libraries before implementation."
    ),
}

# Primary tool -> checklist tool names satisfied by calling the primary (success only).
# Composite tools that satisfy score + gate. Security is NOT implied: quick mode
# and validate_changed(quick=True) often skip bandit / full security scans.
_TOOL_EQUIVALENTS: dict[str, frozenset[str]] = {
    "tapps_quick_check": frozenset({"tapps_score_file", "tapps_quality_gate"}),
    "tapps_validate_changed": frozenset({"tapps_score_file", "tapps_quality_gate"}),
    # Docs-routed research satisfies the lookup_docs obligation (ADR-0030).
    "tapps_research": frozenset({"tapps_lookup_docs"}),
}

_engagement_maps_cache: dict[str, dict[str, dict[str, list[str]]]] | None = None
_engagement_maps_version: str = ""
_engagement_maps_root: str | None = None
_engagement_maps_extras_fp: str | None = None


def invalidate_engagement_maps_cache() -> None:
    """Clear merged policy cache (tests / policy file edits)."""
    global _engagement_maps_cache, _engagement_maps_version, _engagement_maps_root
    global _engagement_maps_extras_fp
    _engagement_maps_cache = None
    _engagement_maps_version = ""
    _engagement_maps_root = None
    _engagement_maps_extras_fp = None


def _get_merged_engagement_maps(
    project_root: Path | None,
) -> tuple[dict[str, dict[str, dict[str, list[str]]]], str]:
    from tapps_mcp.tools.checklist_policy import (
        compute_policy_version,
        load_checklist_policy_extras,
        merge_engagement_maps,
    )

    global _engagement_maps_cache, _engagement_maps_version, _engagement_maps_root
    global _engagement_maps_extras_fp
    root = (project_root or Path.cwd()).resolve()
    extras = load_checklist_policy_extras(root)
    fp = extras.content_fingerprint if extras else ""
    key = str(root)
    if (
        _engagement_maps_cache is not None
        and _engagement_maps_root == key
        and _engagement_maps_extras_fp == fp
    ):
        return _engagement_maps_cache, _engagement_maps_version
    merged = merge_engagement_maps(_ENGAGEMENT_TOOL_MAP, extras)
    ver = compute_policy_version(merged, extras)
    _engagement_maps_cache = merged
    _engagement_maps_version = ver
    _engagement_maps_root = key
    _engagement_maps_extras_fp = fp
    return merged, ver
