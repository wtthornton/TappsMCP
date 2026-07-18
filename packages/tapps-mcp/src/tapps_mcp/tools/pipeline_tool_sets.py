"""Shared TAPPS pipeline tool identifiers for stop-hook transcript parsing (TAP-3922).

Centralizes gate/checklist/lookup tool short names and NLT MCP server prefixes so
Claude inline stop-hook scripts, ``loop_metrics``, and ``usage`` agree on which
transcript tool calls count as pipeline compliance.
"""

from __future__ import annotations

import re
from typing import Any, Final

from tapps_mcp.distribution.nlt_mcp_config import LEGACY_NLT_SERVER_IDS, NLT_SERVER_ORDER

_CALLMCPTOOL_NAME = "CallMcpTool"

GATE_SHORT_NAMES: Final[frozenset[str]] = frozenset(
    {"tapps_quick_check", "tapps_validate_changed", "tapps_quality_gate"}
)
CHECKLIST_SHORT_NAMES: Final[frozenset[str]] = frozenset({"tapps_checklist"})
LOOKUP_SHORT_NAMES: Final[frozenset[str]] = frozenset({"tapps_lookup_docs"})
# Code-comprehension tools (callers/blast-radius before a cross-cutting change).
# Shared so both the usage-gap check and the rolling adoption metric agree.
COMPREHENSION_SHORT_NAMES: Final[frozenset[str]] = frozenset(
    {"tapps_call_graph", "tapps_impact_analysis", "tapps_dependency_graph"}
)
EDIT_TOOL_NAMES: Final[frozenset[str]] = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
SOURCE_FILE_SUFFIXES: Final[tuple[str, ...]] = (
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
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


def resolve_callmcptool_tool_name(tool_input: dict[str, Any]) -> str | None:
    """Return ``toolName`` from a Cursor ``CallMcpTool`` envelope when present."""
    for key in ("toolName", "tool_name"):
        raw = tool_input.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def is_tapps_mcp_server(server: str) -> bool:
    """True when *server* looks like a TappsMCP or NLT MCP host identifier."""
    lowered = server.lower().rsplit("/", 1)[-1]
    # Cursor project-prefixed: project-0-tapps-mcp-nlt-build
    name = re.sub(r"^project-\d+-", "", lowered)
    if name in MCP_SERVER_PREFIXES:
        return True
    return any(name == marker or name.endswith("-" + marker) for marker in MCP_SERVER_PREFIXES)


def resolve_transcript_tool_name(name: str, tool_input: dict[str, Any]) -> str:
    """Map Cursor ``CallMcpTool`` to the inner ``tapps_*`` tool name when present."""
    if name == _CALLMCPTOOL_NAME:
        inner = resolve_callmcptool_tool_name(tool_input)
        if inner:
            return inner
    return name


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
    "COMPREHENSION_SHORT_NAMES",
    "EDIT_TOOL_NAMES",
    "GATE_SHORT_NAMES",
    "LOOKUP_SHORT_NAMES",
    "MCP_SERVER_PREFIXES",
    "SOURCE_FILE_SUFFIXES",
    "is_checklist_tool",
    "is_gate_tool",
    "is_lookup_tool",
    "is_tapps_mcp_server",
    "matches_pipeline_tool",
    "resolve_callmcptool_tool_name",
    "resolve_transcript_tool_name",
]
