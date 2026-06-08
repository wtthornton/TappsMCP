"""TAP-1963: CI gate on registered MCP tool description lengths.

Enumerates actually-registered tools from the tapps-mcp and docs-mcp FastMCP
instances (not a regex over source). Retired tools such as ``tapps_memory`` are
excluded automatically because they are no longer in the registry.
"""

from __future__ import annotations

import statistics

import pytest

from docs_mcp.server import ALL_DOCS_TOOL_NAMES
from docs_mcp.server import mcp as docs_mcp
from docs_mcp.tool_descriptions import HARD_MAX_CHARS as DOCS_HARD_MAX
from docs_mcp.tool_descriptions import MEDIAN_MAX_CHARS as DOCS_MEDIAN_MAX
from tapps_mcp.server import ALL_TOOL_NAMES
from tapps_mcp.server import mcp as tapps_mcp
from tapps_mcp.tool_descriptions import HARD_MAX_CHARS as TAPPS_HARD_MAX
from tapps_mcp.tool_descriptions import MEDIAN_MAX_CHARS as TAPPS_MEDIAN_MAX

_MEDIAN_MAX = min(TAPPS_MEDIAN_MAX, DOCS_MEDIAN_MAX)
_HARD_MAX = min(TAPPS_HARD_MAX, DOCS_HARD_MAX)


def _registered_descriptions(mcp) -> dict[str, str]:
    return {name: (tool.description or "") for name, tool in mcp._tool_manager._tools.items()}


class TestTappsToolDescriptions:
    def test_registry_matches_canonical_names(self) -> None:
        registered = set(tapps_mcp._tool_manager._tools)
        assert registered == set(ALL_TOOL_NAMES)

    def test_median_under_budget(self) -> None:
        lengths = [len(d) for d in _registered_descriptions(tapps_mcp).values()]
        median = statistics.median(lengths)
        assert median < _MEDIAN_MAX, (
            f"tapps-mcp median description length {median:.1f} >= {_MEDIAN_MAX}"
        )

    def test_max_under_hard_cap(self) -> None:
        descriptions = _registered_descriptions(tapps_mcp)
        offenders = {name: len(desc) for name, desc in descriptions.items() if len(desc) > _HARD_MAX}
        assert not offenders, f"tapps-mcp descriptions exceed {_HARD_MAX} chars: {offenders}"


class TestDocsToolDescriptions:
    def test_registry_matches_canonical_names(self) -> None:
        registered = set(docs_mcp._tool_manager._tools)
        assert registered == set(ALL_DOCS_TOOL_NAMES)

    def test_median_under_budget(self) -> None:
        lengths = [len(d) for d in _registered_descriptions(docs_mcp).values()]
        median = statistics.median(lengths)
        assert median < _MEDIAN_MAX, (
            f"docs-mcp median description length {median:.1f} >= {_MEDIAN_MAX}"
        )

    def test_max_under_hard_cap(self) -> None:
        descriptions = _registered_descriptions(docs_mcp)
        offenders = {name: len(desc) for name, desc in descriptions.items() if len(desc) > _HARD_MAX}
        assert not offenders, f"docs-mcp descriptions exceed {_HARD_MAX} chars: {offenders}"


class TestCombinedCatalog:
    def test_combined_median_under_budget(self) -> None:
        all_lengths = [
            len(d)
            for mcp in (tapps_mcp, docs_mcp)
            for d in _registered_descriptions(mcp).values()
        ]
        median = statistics.median(all_lengths)
        assert median < _MEDIAN_MAX, f"combined median {median:.1f} >= {_MEDIAN_MAX}"

    @pytest.mark.parametrize(
        ("server_label", "mcp"),
        [
            ("tapps-mcp", tapps_mcp),
            ("docs-mcp", docs_mcp),
        ],
    )
    def test_no_empty_descriptions(self, server_label: str, mcp) -> None:
        empty = [name for name, desc in _registered_descriptions(mcp).items() if not desc.strip()]
        assert not empty, f"{server_label} tools with empty descriptions: {empty}"
