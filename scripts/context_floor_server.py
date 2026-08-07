"""Server-instruction measurement for the context-efficiency epic (SG0).

Finds ``FastMCP(..., instructions=...)`` blocks in the tapps-mcp/docs-mcp
server modules and multiplies each by the number of deployed NLT server
bundles (``NLT_SERVER_SPECS`` in ``nlt_mcp_config.py``) that actually launch
that module -- a block shipped by N separate MCP connections costs N times
per session, not once.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from context_floor_core import (
    _DOCS_MCP_SRC,
    _REPO_ROOT,
    _TAPPS_MCP_SRC,
    MeasurementError,
    _assign_target,
    _literal_dict_value,
    _parse,
    tokens,
)

# Which CLI entry point (a package's [project.scripts] name, per
# pyproject.toml) launches which server module. "tapps-platform" (the
# combined server) is intentionally absent: it copies already-built Tool
# objects from the tapps-mcp/docs-mcp servers rather than re-registering
# them, and passes no instructions= of its own -- so it never contributes.
_SERVE_COMMAND_TO_SERVER_FILE: dict[str, Path] = {
    "tapps-mcp": _TAPPS_MCP_SRC / "tapps_mcp" / "server.py",
    "docsmcp": _DOCS_MCP_SRC / "docs_mcp" / "server.py",
}
_NLT_MCP_CONFIG = _TAPPS_MCP_SRC / "tapps_mcp" / "distribution" / "nlt_mcp_config.py"


def _count_bundles_by_serve_command(path: Path) -> dict[str, int]:
    """Count NLT_SERVER_SPECS entries per ``serve_command`` -- each entry is
    a separate deployed MCP server connection (a distinct ``.mcp.json``
    entry), so N entries sharing a serve_command means the module they
    launch sends its instructions= text N times per session.
    """
    if not path.exists():
        raise MeasurementError(f"NLT server spec module not found: {path}")
    specs_node: ast.Dict | None = None
    for node in _parse(path).body:
        target, value = _assign_target(node)
        if target == "NLT_SERVER_SPECS" and isinstance(value, ast.Dict):
            specs_node = value
            break
    if specs_node is None:
        raise MeasurementError(f"NLT_SERVER_SPECS dict literal not found in {path}")

    counts: dict[str, int] = {}
    for entry in specs_node.values:
        if not isinstance(entry, ast.Dict):
            continue
        serve_command = _literal_dict_value(entry, "serve_command")
        if isinstance(serve_command, str):
            counts[serve_command] = counts.get(serve_command, 0) + 1
    return counts


def _find_fastmcp_instructions_exprs(path: Path) -> list[ast.expr]:
    """Return the ``instructions=`` keyword value expressions from every
    ``FastMCP(...)`` call in *path*."""
    exprs: list[ast.expr] = []
    for node in ast.walk(_parse(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "FastMCP"
        ):
            for keyword in node.keywords:
                if keyword.arg == "instructions":
                    exprs.append(keyword.value)
    return exprs


def _resolve_string_constant(expr: ast.expr, source_file: Path) -> str:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.Name):
        for node in _parse(source_file).body:
            target, value = _assign_target(node)
            if (
                target == expr.id
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                return value.value
        raise MeasurementError(f"could not resolve constant {expr.id!r} in {source_file}")
    raise MeasurementError(
        f"unsupported instructions= expression in {source_file}: {ast.dump(expr)[:80]}"
    )


def measure_server_instructions() -> tuple[int, list[dict[str, Any]]]:
    bundle_counts = _count_bundles_by_serve_command(_NLT_MCP_CONFIG)
    detail: list[dict[str, Any]] = []
    total_tokens = 0
    for serve_command, server_file in _SERVE_COMMAND_TO_SERVER_FILE.items():
        if not server_file.exists():
            raise MeasurementError(f"server module not found: {server_file}")
        for expr in _find_fastmcp_instructions_exprs(server_file):
            text = _resolve_string_constant(expr, server_file)
            byte_count = len(text.encode("utf-8"))
            per_bundle_tokens = tokens(text)
            bundle_count = bundle_counts.get(serve_command, 0)
            total_tokens += per_bundle_tokens * bundle_count
            detail.append(
                {
                    "source_file": str(server_file.relative_to(_REPO_ROOT)),
                    "serve_command": serve_command,
                    "bytes": byte_count,
                    "tokens_per_bundle": per_bundle_tokens,
                    "bundle_count": bundle_count,
                    "total_tokens": per_bundle_tokens * bundle_count,
                }
            )
    return total_tokens, detail
