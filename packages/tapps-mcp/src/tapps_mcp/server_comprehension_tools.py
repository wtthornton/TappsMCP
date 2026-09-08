"""Comprehension tool handlers for TappsMCP: tapps_file_api, tapps_repo_map.

Split out of server_analysis_tools.py (LANE_ISSUE round 2) to keep the
megafile's quality score from regressing on every future addition. Handler
bodies live in project/file_api.py / project/repo_map.py; the functions here
are the thin MCP-tool envelopes registered on the ``mcp`` instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from tapps_mcp.mcp_register import register_tool

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# TAP-961 / TAP-1986: large-output, on-demand reads — deferred, not daily-drivers.
_META_LARGE_OUTPUT_100K_D: dict[str, Any] = {
    "anthropic/maxResultSizeChars": 100_000,
    "defer_loading": True,
}


async def tapps_file_api(
    file_path: str, project_root: str = "", force_rebuild: bool = False
) -> dict[str, Any]:
    """Every indexed symbol in a file with its header line (docs/CALL_GRAPH.md)."""
    from tapps_mcp.project.file_api import run_tapps_file_api

    return await run_tapps_file_api(file_path, project_root, force_rebuild)


async def tapps_repo_map(
    project_root: str = "",
    token_budget: int = 4000,
    max_dirs: int = 16,
    force_rebuild: bool = False,
) -> dict[str, Any]:
    """Directory-level map: symbol/edge clusters and hubs (docs/CALL_GRAPH.md)."""
    from tapps_mcp.project.repo_map import run_tapps_repo_map

    return await run_tapps_repo_map(project_root, token_budget, max_dirs, force_rebuild)


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register comprehension tools present in ``allowed_tools``."""
    if "tapps_file_api" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_file_api,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_LARGE_OUTPUT_100K_D,
        )
    if "tapps_repo_map" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_repo_map,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_LARGE_OUTPUT_100K_D,
        )
