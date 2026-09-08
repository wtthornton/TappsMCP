"""VAL-05 (ADR-0016): no MCP-registered tool may carry a live `[DEPRECATED` marker.

`tapps_memory` used to ship `[DEPRECATED 2026-Q3 — use mcp__tapps-brain__*]`
in its own docstring while ADR-0016 / TAP-3895 had already reinstated it as
the sanctioned `nlt-memory` facade — the code and the decision disagreed.
This test scans every tool name reachable from any `TOOL_PROFILE_*` in
`server.py`, resolves its callable across the `server_*_tools` modules, and
fails if either the callable's docstring or its registered
`TOOL_DESCRIPTIONS` entry still carries `[DEPRECATED`.
"""

from __future__ import annotations

import importlib
from typing import Any

_TOOL_MODULE_NAMES: tuple[str, ...] = (
    "tapps_mcp.server_analysis_tools",
    "tapps_mcp.server_checklist_tools",
    "tapps_mcp.server_linear_tools",
    "tapps_mcp.server_lookup_tools",
    "tapps_mcp.server_memory_tools",
    "tapps_mcp.server_metrics_tools",
    "tapps_mcp.server_pipeline_tools",
    "tapps_mcp.server_release_tools",
    "tapps_mcp.server_research_tools",
    "tapps_mcp.server_scoring_tools",
    "tapps_mcp.server_skill_tools",
    "tapps_mcp.server_system_tools",
)


def _all_tool_profile_names() -> set[str]:
    """Union of every ``TOOL_PROFILE_*`` frozenset exported by server.py."""
    from tapps_mcp import server

    names: set[str] = set()
    for attr in dir(server):
        if not attr.startswith("TOOL_PROFILE_"):
            continue
        value = getattr(server, attr)
        if isinstance(value, frozenset):
            names |= value
    return names


def _resolve_tool_callable(tool_name: str) -> Any | None:
    """Find the plain function backing *tool_name* across the tool modules."""
    for module_name in _TOOL_MODULE_NAMES:
        module = importlib.import_module(module_name)
        candidate = getattr(module, tool_name, None)
        if callable(candidate):
            return candidate
    return None


def test_tool_profile_union_is_non_empty() -> None:
    """Sanity: the discovery mechanism itself must find real tool profiles."""
    names = _all_tool_profile_names()
    assert len(names) > 10, f"expected a substantial tool catalog, got {sorted(names)}"
    assert "tapps_memory" in names, "tapps_memory must live on some TOOL_PROFILE_* (nlt-memory)"


def test_tapps_memory_callable_is_resolvable() -> None:
    """Sanity: the resolver must actually find tapps_memory's function."""
    fn = _resolve_tool_callable("tapps_memory")
    assert fn is not None, "resolver failed to locate tapps_memory — fix the resolver first"


def test_no_registered_tool_docstring_or_description_says_deprecated() -> None:
    """No tool reachable from any profile may carry a live [DEPRECATED marker.

    A callable that cannot be resolved (pointer stub, prompt, resource) is
    skipped rather than failed — this test's contract is about docstrings
    and descriptions that exist, not about resolving every registration
    mechanism in the codebase.
    """
    from tapps_mcp.tool_descriptions import TOOL_DESCRIPTIONS

    offenders: list[str] = []
    for tool_name in sorted(_all_tool_profile_names()):
        fn = _resolve_tool_callable(tool_name)
        doc = (fn.__doc__ or "") if fn is not None else ""
        description = TOOL_DESCRIPTIONS.get(tool_name, "")
        if "[DEPRECATED" in doc or "[DEPRECATED" in description:
            offenders.append(tool_name)

    assert not offenders, (
        f"these registered tools still carry a live [DEPRECATED marker: {offenders}"
    )
