"""Shared primitives for the ``context_floor_*`` modules (SG0, context-efficiency epic).

Path constants, the fixed token estimator, the ``MeasurementError`` used for
every expected (non-bug) measurement failure, and the small generic ``ast``
helpers every other ``context_floor_*`` module builds on. Everything in this
package measures from source via ``ast`` -- never via a live MCP handshake;
see ``measure_context_floor.py``'s module docstring for why.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TAPPS_MCP_SRC = _REPO_ROOT / "packages" / "tapps-mcp" / "src"
_DOCS_MCP_SRC = _REPO_ROOT / "packages" / "docs-mcp" / "src"
_TAPPS_CORE_SRC = _REPO_ROOT / "packages" / "tapps-core" / "src"
_PIPELINE_DIR = _TAPPS_MCP_SRC / "tapps_mcp" / "pipeline"
_TOOLS_DIR = _TAPPS_MCP_SRC / "tapps_mcp" / "tools"
_RULES_DIR = _REPO_ROOT / ".claude" / "rules"
_CLAUDE_MD = _REPO_ROOT / "CLAUDE.md"
_REGISTER_HELPER_NAME = "mcp_register.py"
_TOOL_ROOTS = (_TAPPS_MCP_SRC, _DOCS_MCP_SRC)


class MeasurementError(RuntimeError):
    """Raised for an expected, user-facing measurement failure.

    Distinguished from an unhandled bug: the caller prints the message and
    exits 1 instead of letting a bare traceback stand in for a diagnosis.
    """


def tokens(text: str) -> int:
    """Fixed token estimator: bytes / 4, rounded. Do not substitute."""
    return round(len(text.encode("utf-8")) / 4)


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _assign_target(node: ast.stmt) -> tuple[str | None, ast.expr | None]:
    """Return (name, value) for a simple ``NAME = value`` or ``NAME: T = value``."""
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id, node.value
    if (
        isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.value is not None
    ):
        return node.target.id, node.value
    return None, None


def _dict_value_node(node: ast.Dict, key: str) -> ast.expr | None:
    """Return the value AST node for *key* in a ``Dict`` literal, if present."""
    for k, v in zip(node.keys, node.values, strict=True):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    return None


def _literal_dict_value(node: ast.Dict, key: str) -> Any | None:
    """Return the Python value for *key* in a ``Dict`` literal iff it is a
    literal (``ast.literal_eval``-able). Non-literal values (function calls,
    comprehensions, other dynamic expressions) return ``None`` -- callers
    treat that as "not statically knowable", not "absent"."""
    value = _dict_value_node(node, key)
    if value is None:
        return None
    try:
        return ast.literal_eval(value)
    except (ValueError, TypeError):
        return None


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _find_return_dict(fn_node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Dict | None:
    """Find the ``ast.Dict`` literal backing a function's return value.

    Handles both ``return {...}`` directly and the common
    ``data = {...}; ...; return data`` shape (the dict is mutated a bit
    after construction, but the literal keys assigned at construction time
    are exactly what this script needs)."""
    return_node = next(
        (n for n in ast.walk(fn_node) if isinstance(n, ast.Return) and n.value is not None), None
    )
    if return_node is None or return_node.value is None:
        return None
    if isinstance(return_node.value, ast.Dict):
        return return_node.value
    if isinstance(return_node.value, ast.Name):
        target_name = return_node.value.id
        for stmt in fn_node.body:
            name, value = _assign_target(stmt)
            if name == target_name and isinstance(value, ast.Dict):
                return value
    return None
