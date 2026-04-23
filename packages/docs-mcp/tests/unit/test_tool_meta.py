"""Tests for TAP-962: large-output docs-mcp tools declare
_meta[anthropic/maxResultSizeChars] so Claude Code keeps results in-context
instead of persisting to disk as a file reference."""

from __future__ import annotations

import pytest

from docs_mcp.server import mcp

_META_KEY = "anthropic/maxResultSizeChars"
_SPEC_MAX = 500_000

EXPECTED_CEILINGS: dict[str, int] = {
    "docs_project_scan": 100_000,
    "docs_module_map": 200_000,
    "docs_api_surface": 100_000,
    "docs_generate_api": 200_000,
    "docs_generate_diagram": 100_000,
    "docs_generate_architecture": 400_000,
    "docs_generate_interactive_diagrams": 400_000,
}


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
