"""Tests for TAP-962 and TAP-1987.

TAP-962: large-output docs-mcp tools declare
_meta[anthropic/maxResultSizeChars] so Claude Code keeps results in-context
instead of persisting to disk as a file reference.

TAP-1987: non-daily-driver tools declare meta["defer_loading"]=True so
Claude Code only loads their schemas on-demand via Tool Search, keeping the
eager catalog ≤ 6 tools.
"""

from __future__ import annotations

import pytest

from docs_mcp.server import mcp

_META_KEY = "anthropic/maxResultSizeChars"
_SPEC_MAX = 500_000

# Daily-driver tools — must be EAGER (no defer_loading).
# Source of truth: docs/architecture/tool-budget.md
_DAILY_DRIVERS: frozenset[str] = frozenset(
    {
        "docs_generate_epic",
        "docs_generate_story",
        "docs_validate_linear_issue",
        "docs_lint_linear_issue",
        "docs_generate_changelog",
        "docs_release_gate",
    }
)

_EAGER_BUDGET = 8  # hard cap from tool-budget.md

EXPECTED_CEILINGS: dict[str, int] = {
    "docs_project_scan": 100_000,
    "docs_module_map": 200_000,
    "docs_api_surface": 100_000,
    "docs_generate_api": 200_000,
    "docs_generate_diagram": 100_000,
    "docs_generate_architecture": 400_000,
    "docs_generate_interactive_diagrams": 400_000,
}


class TestDeferLoading:
    """TAP-1987: verify eager/deferred split matches the tool-budget.md spec."""

    def test_eager_tool_count_within_budget(self) -> None:
        """Eager tool count must be ≤ _EAGER_BUDGET (currently 8)."""
        tools = mcp._tool_manager._tools
        eager = [n for n, t in tools.items() if not (t.meta or {}).get("defer_loading")]
        assert len(eager) <= _EAGER_BUDGET, (
            f"Eager tool count {len(eager)} exceeds budget {_EAGER_BUDGET}. "
            f"Eager tools: {sorted(eager)}"
        )

    def test_daily_drivers_are_eager(self) -> None:
        """Each daily-driver tool must NOT have defer_loading=True."""
        tools = mcp._tool_manager._tools
        for name in _DAILY_DRIVERS:
            assert name in tools, f"Daily-driver {name!r} not registered"
            meta = tools[name].meta or {}
            assert not meta.get("defer_loading"), (
                f"Daily-driver {name!r} has defer_loading=True but should be eager"
            )

    @pytest.mark.parametrize(
        "tool_name",
        sorted(
            [
                "docs_check_drift",
                "docs_generate_adr",
                "docs_generate_readme",
                "docs_module_map",
                "docs_api_surface",
                "docs_session_start",
                "docs_project_scan",
                "docs_config",
                "docs_git_summary",
                "docs_linear_triage",
                "docs_validate_release_update",
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
    def test_at_least_five_tools_annotated(self) -> None:
        tools = mcp._tool_manager._tools
        annotated = [
            name
            for name in EXPECTED_CEILINGS
            if name in tools and tools[name].meta and _META_KEY in (tools[name].meta or {})
        ]
        assert len(annotated) >= 5, (
            f"Expected >=5 large-output tools with {_META_KEY}, got {len(annotated)}: {annotated}"
        )

    @pytest.mark.parametrize("tool_name", sorted(EXPECTED_CEILINGS))
    def test_meta_max_result_size_set(self, tool_name: str) -> None:
        tools = mcp._tool_manager._tools
        assert tool_name in tools, f"Tool {tool_name} not registered"
        meta = tools[tool_name].meta
        assert meta is not None, f"{tool_name} has no _meta"
        assert _META_KEY in meta, f"{tool_name}._meta missing {_META_KEY!r}: {meta}"
        expected = EXPECTED_CEILINGS[tool_name]
        assert meta[_META_KEY] == expected, (
            f"{tool_name}._meta[{_META_KEY}]={meta[_META_KEY]}, expected {expected}"
        )
        assert meta[_META_KEY] < _SPEC_MAX, (
            f"{tool_name} ceiling {meta[_META_KEY]} exceeds MCP spec max {_SPEC_MAX}"
        )
