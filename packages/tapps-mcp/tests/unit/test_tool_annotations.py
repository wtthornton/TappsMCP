"""Tests for MCP tool annotations (Story 12.1).

Verifies that all 29 registered tools have correct ToolAnnotations set,
ensuring MCP clients can auto-approve read-only tools and skip destructive
action warnings.
"""

from __future__ import annotations

import pytest
from mcp.types import ToolAnnotations

from tapps_mcp.server import mcp

# ---------------------------------------------------------------------------
# Expected annotations per tool
# ---------------------------------------------------------------------------

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_READ_ONLY_OPEN = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

_SIDE_EFFECT_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_SIDE_EFFECT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

# Cache invalidation legitimately marks destructiveHint=True — see
# server_linear_tools._ANNOTATIONS_INVALIDATE. The data is recomputable
# (re-fetch from Linear), but the operation deletes cache state, which is
# the literal MCP definition of a destructive update.
_DESTRUCTIVE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)

EXPECTED_ANNOTATIONS: dict[str, ToolAnnotations] = {
    # Read-only, idempotent, closed-world (19 tools)
    "tapps_server_info": _READ_ONLY,
    "tapps_security_scan": _READ_ONLY,
    "tapps_score_file": _READ_ONLY,
    "tapps_quality_gate": _READ_ONLY,
    "tapps_quick_check": _READ_ONLY,
    "tapps_validate_changed": _READ_ONLY,
    "tapps_validate_config": _READ_ONLY,
    "tapps_checklist": _READ_ONLY,
    "tapps_session_notes": _READ_ONLY,
    "tapps_impact_analysis": _READ_ONLY,
    "tapps_report": _READ_ONLY,
    "tapps_dashboard": _READ_ONLY,
    "tapps_stats": _READ_ONLY,
    "tapps_dead_code": _READ_ONLY,
    "tapps_dependency_graph": _READ_ONLY,
    "tapps_doctor": _READ_ONLY,
    "tapps_pipeline": _READ_ONLY,
    "tapps_decompose": _READ_ONLY,
    "tapps_linear_snapshot_get": _READ_ONLY,
    # Read-only, open-world (2 tools)
    "tapps_lookup_docs": _READ_ONLY_OPEN,
    "tapps_dependency_scan": _READ_ONLY_OPEN,
    # Side-effect, idempotent (7 tools)
    "tapps_session_start": _SIDE_EFFECT_IDEMPOTENT,
    "tapps_session_end": _SIDE_EFFECT_IDEMPOTENT,
    "tapps_handoff_save": _SIDE_EFFECT_IDEMPOTENT,
    "tapps_init": _SIDE_EFFECT_IDEMPOTENT,
    "tapps_upgrade": _SIDE_EFFECT_IDEMPOTENT,
    "tapps_set_engagement_level": _SIDE_EFFECT_IDEMPOTENT,
    "tapps_linear_snapshot_put": _SIDE_EFFECT_IDEMPOTENT,
    "tapps_audit_close_coverage": _SIDE_EFFECT_IDEMPOTENT,  # TAP-2798
    # Side-effect, non-idempotent (1 tool — TAP-1994: tapps_memory removed from catalog)
    "tapps_feedback": _SIDE_EFFECT,
    # Destructive, idempotent (1 tool — cache eviction)
    "tapps_linear_snapshot_invalidate": _DESTRUCTIVE_IDEMPOTENT,
}

# Tools allowed to set destructiveHint=True. Cache eviction is the only one
# today; expand explicitly when adding new destructive tools so it is a
# deliberate decision rather than a silent regression.
_ALLOWED_DESTRUCTIVE: frozenset[str] = frozenset({"tapps_linear_snapshot_invalidate"})


class TestToolAnnotationsPresent:
    """Every registered tool must have annotations set (not None)."""

    def test_all_tools_registered(self) -> None:
        from tapps_mcp.server import ALL_TOOL_NAMES

        tools = mcp._tool_manager._tools
        assert len(tools) == len(ALL_TOOL_NAMES), (
            f"Expected {len(ALL_TOOL_NAMES)} tools, got {len(tools)}: {sorted(tools)}"
        )

    def test_all_tools_have_annotations(self) -> None:
        tools = mcp._tool_manager._tools
        missing = [name for name, tool in tools.items() if tool.annotations is None]
        assert not missing, f"Tools missing annotations: {missing}"

    def test_destructive_tools_only_in_allowlist(self) -> None:
        tools = mcp._tool_manager._tools
        destructive = {
            name
            for name, tool in tools.items()
            if tool.annotations and tool.annotations.destructiveHint
        }
        unexpected = destructive - _ALLOWED_DESTRUCTIVE
        assert not unexpected, (
            f"Tools marked destructive without being on the allowlist: {sorted(unexpected)}. "
            f"Add to _ALLOWED_DESTRUCTIVE in this file if intentional."
        )


class TestToolAnnotationValues:
    """Each tool's annotations must match the expected category."""

    @pytest.mark.parametrize("tool_name", sorted(EXPECTED_ANNOTATIONS))
    def test_annotation_matches(self, tool_name: str) -> None:
        tools = mcp._tool_manager._tools
        assert tool_name in tools, f"Tool {tool_name} not registered"
        actual = tools[tool_name].annotations
        expected = EXPECTED_ANNOTATIONS[tool_name]
        assert actual is not None, f"{tool_name} has no annotations"
        assert actual.readOnlyHint == expected.readOnlyHint, (
            f"{tool_name}: readOnlyHint={actual.readOnlyHint}, expected={expected.readOnlyHint}"
        )
        assert actual.destructiveHint == expected.destructiveHint, (
            f"{tool_name}: destructiveHint={actual.destructiveHint}, "
            f"expected={expected.destructiveHint}"
        )
        assert actual.idempotentHint == expected.idempotentHint, (
            f"{tool_name}: idempotentHint={actual.idempotentHint}, "
            f"expected={expected.idempotentHint}"
        )
        assert actual.openWorldHint == expected.openWorldHint, (
            f"{tool_name}: openWorldHint={actual.openWorldHint}, expected={expected.openWorldHint}"
        )


class TestAnnotationCategories:
    """Verify the expected distribution of annotation categories."""

    def test_read_only_count(self) -> None:
        tools = mcp._tool_manager._tools
        read_only = [
            name
            for name, tool in tools.items()
            if tool.annotations and tool.annotations.readOnlyHint
        ]
        # 18 closed-world + 2 open-world + 1 linear-snapshot-get + 1 release-update
        # + 1 tapps_linear_count (TAP-1847) + 1 tapps_audit_campaign (TAP-2036)
        # + 1 tapps_usage (v3.11.0) + 1 tapps_linear_list_issues (TAP-2010)
        # + 1 tapps_finding_to_story (TAP-2717) = 27
        assert len(read_only) == 27, (
            f"Expected 27 read-only tools, got {len(read_only)}"
        )

    def test_side_effect_count(self) -> None:
        tools = mcp._tool_manager._tools
        side_effect = [
            name
            for name, tool in tools.items()
            if tool.annotations and not tool.annotations.readOnlyHint
        ]
        # 5 idempotent + 1 non-idempotent (tapps_feedback) + linear-snapshot-put
        # + linear-snapshot-invalidate = 8 (TAP-1994: tapps_memory removed)
        # + 2 hive elevation tools (TAP-2014)
        # + 1 tapps_audit_close_coverage (TAP-2798) + 1 tapps_handoff_save (TAP-3792) = 12.
        assert len(side_effect) == 12, (
            f"Expected 12 side-effect tools, got {len(side_effect)}"
        )

    def test_open_world_count(self) -> None:
        tools = mcp._tool_manager._tools
        open_world = [
            name
            for name, tool in tools.items()
            if tool.annotations and tool.annotations.openWorldHint
        ]
        assert len(open_world) == 2, (
            f"Expected 2 open-world tools, got {len(open_world)}"
        )  # TAP-483: -2

    def test_idempotent_count(self) -> None:
        tools = mcp._tool_manager._tools
        idempotent = [
            name
            for name, tool in tools.items()
            if tool.annotations and tool.annotations.idempotentHint
        ]
        # 22 prior + 3 linear-snapshot + 1 release-update + 1 tapps_linear_count (TAP-1847)
        # + 1 tapps_audit_campaign (TAP-2036) + 1 tapps_session_end (TAP-2005)
        # + 1 tapps_usage (v3.11.0) + 1 tapps_linear_list_issues (TAP-2010)
        # + 1 tapps_finding_to_story (TAP-2717)
        # + 1 tapps_audit_close_coverage (TAP-2798) + 1 tapps_handoff_save (TAP-3792) = 34
        assert len(idempotent) == 34, (
            f"Expected 33 idempotent tools, got {len(idempotent)}: {sorted(idempotent)}"
        )


class TestDeferLoading:
    """TAP-1986: verify eager/deferred split keeps the eager catalog ≤ 9 tools.

    v3.11.0 added tapps_usage as the 9th eager tool — it is intentionally
    not deferred because it is part of the end-of-task pipeline alongside
    tapps_checklist. See server_metrics_tools.register().
    """

    # Daily-driver tools — must be EAGER (no defer_loading).
    _DAILY_DRIVERS: frozenset[str] = frozenset(
        {
            "tapps_session_start",
            "tapps_validate_changed",
            "tapps_score_file",
            "tapps_quality_gate",
            "tapps_quick_check",
            "tapps_lookup_docs",
            "tapps_checklist",
            "tapps_impact_analysis",
        }
    )
    _EAGER_BUDGET = 9

    def test_eager_tool_count_within_budget(self) -> None:
        """Eager tool count must be ≤ _EAGER_BUDGET (currently 9)."""
        tools = mcp._tool_manager._tools
        eager = [n for n, t in tools.items() if not (t.meta or {}).get("defer_loading")]
        assert len(eager) <= self._EAGER_BUDGET, (
            f"Eager tool count {len(eager)} exceeds budget {self._EAGER_BUDGET}. "
            f"Eager tools: {sorted(eager)}"
        )

    def test_daily_drivers_are_eager(self) -> None:
        """Each daily-driver tool must NOT have defer_loading=True."""
        tools = mcp._tool_manager._tools
        for name in self._DAILY_DRIVERS:
            assert name in tools, f"Daily-driver {name!r} not registered"
            meta = tools[name].meta or {}
            assert not meta.get("defer_loading"), (
                f"Daily-driver {name!r} has defer_loading=True but should be eager"
            )

    @pytest.mark.parametrize(
        "tool_name",
        sorted(
            [
                "tapps_server_info",
                "tapps_security_scan",
                "tapps_validate_config",
                "tapps_init",
                "tapps_set_engagement_level",
                "tapps_upgrade",
                "tapps_doctor",
                "tapps_pipeline",
                "tapps_decompose",
                "tapps_dashboard",
                "tapps_stats",
                "tapps_feedback",
                "tapps_session_notes",
                "tapps_report",
                "tapps_dead_code",
                "tapps_dependency_scan",
                "tapps_dependency_graph",
                "tapps_audit_campaign",
                "tapps_linear_snapshot_get",
                "tapps_linear_snapshot_put",
                "tapps_linear_snapshot_invalidate",
                "tapps_linear_count",
                "tapps_release_update",
            ]
        ),
    )
    def test_deferred_tools_have_flag(self, tool_name: str) -> None:
        """Non-daily-driver tools must have meta[defer_loading]=True."""
        tools = mcp._tool_manager._tools
        assert tool_name in tools, f"Tool {tool_name!r} not registered"
        meta = tools[tool_name].meta or {}
        assert meta.get("defer_loading") is True, (
            f"{tool_name!r} missing defer_loading=True in meta: {meta}"
        )


class TestLargeOutputMeta:
    """TAP-961: large-output analysis tools declare _meta[anthropic/maxResultSizeChars]
    so Claude Code keeps results in-context instead of persisting to disk."""

    _EXPECTED_CEILINGS: dict[str, int] = {
        "tapps_impact_analysis": 100_000,
        "tapps_report": 100_000,
        "tapps_dead_code": 100_000,
        "tapps_dependency_graph": 200_000,
    }

    @pytest.mark.parametrize("tool_name", sorted(_EXPECTED_CEILINGS))
    def test_meta_max_result_size_set(self, tool_name: str) -> None:
        tools = mcp._tool_manager._tools
        assert tool_name in tools, f"Tool {tool_name} not registered"
        tool = tools[tool_name]
        meta = tool.meta
        assert meta is not None, f"{tool_name} has no _meta"
        key = "anthropic/maxResultSizeChars"
        assert key in meta, f"{tool_name}._meta missing {key!r}: {meta}"
        assert meta[key] == self._EXPECTED_CEILINGS[tool_name], (
            f"{tool_name}._meta[{key}]={meta[key]}, "
            f"expected {self._EXPECTED_CEILINGS[tool_name]}"
        )
        assert meta[key] < 500_000, (
            f"{tool_name} ceiling {meta[key]} exceeds MCP spec max 500000"
        )
