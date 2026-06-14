"""Shared TAPPS pipeline tool identifiers for stop-hook transcript parsing (TAP-3922).

Centralizes gate/checklist/lookup tool short names and NLT MCP server prefixes so
Claude inline stop-hook scripts, ``loop_metrics``, and ``usage`` agree on which
transcript tool calls count as pipeline compliance.
"""

from __future__ import annotations

from typing import Final

from tapps_mcp.distribution.nlt_mcp_config import LEGACY_NLT_SERVER_IDS, NLT_SERVER_ORDER

GATE_SHORT_NAMES: Final[frozenset[str]] = frozenset(
    {"tapps_quick_check", "tapps_validate_changed", "tapps_quality_gate"}
)
CHECKLIST_SHORT_NAMES: Final[frozenset[str]] = frozenset({"tapps_checklist"})
LOOKUP_SHORT_NAMES: Final[frozenset[str]] = frozenset({"tapps_lookup_docs"})
EDIT_TOOL_NAMES: Final[frozenset[str]] = frozenset(
    {"Edit", "Write", "MultiEdit", "NotebookEdit"}
)
SOURCE_FILE_SUFFIXES: Final[tuple[str, ...]] = (
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
)

# Legacy + NLT server IDs that expose tapps_* tools via MCP (ADR-0016).
MCP_SERVER_PREFIXES: Final[frozenset[str]] = frozenset(
    {
        "tapps-mcp",
        "tapps-quality",
        "tapps-setup",
        "docs-mcp",
        *NLT_SERVER_ORDER,
        *LEGACY_NLT_SERVER_IDS.keys(),
    }
)


def matches_pipeline_tool(name: str, short_names: frozenset[str]) -> bool:
    """Return True when *name* is a bare or MCP-prefixed pipeline tool."""
    if name in short_names:
        return True
    if not name.startswith("mcp__"):
        return False
    parts = name.split("__")
    if len(parts) < 3:
        return False
    tail = parts[-1]
    return tail in short_names


def is_gate_tool(name: str) -> bool:
    return matches_pipeline_tool(name, GATE_SHORT_NAMES)


def is_checklist_tool(name: str) -> bool:
    return matches_pipeline_tool(name, CHECKLIST_SHORT_NAMES)


def is_lookup_tool(name: str) -> bool:
    return matches_pipeline_tool(name, LOOKUP_SHORT_NAMES)


__all__ = [
    "CHECKLIST_SHORT_NAMES",
    "EDIT_TOOL_NAMES",
    "GATE_SHORT_NAMES",
    "LOOKUP_SHORT_NAMES",
    "MCP_SERVER_PREFIXES",
    "SOURCE_FILE_SUFFIXES",
    "is_checklist_tool",
    "is_gate_tool",
    "is_lookup_tool",
    "matches_pipeline_tool",
]
