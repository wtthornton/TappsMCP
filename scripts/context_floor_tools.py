"""Tool-schema measurement for the context-efficiency epic (SG0).

Discovers every distinct ``register_tool()``-registered MCP tool across
tapps-mcp and docs-mcp and reconstructs the JSON Schema FastMCP/pydantic
emits for each, entirely from source via ``ast``.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from context_floor_core import (
    _REGISTER_HELPER_NAME,
    _REPO_ROOT,
    _TOOL_ROOTS,
    MeasurementError,
    _parse,
)


@dataclass
class ToolInfo:
    name: str
    source_file: str
    docstring_bytes: int
    param_bytes: int

    @property
    def total_bytes(self) -> int:
        return self.docstring_bytes + self.param_bytes


def _is_register_tool_call(node: ast.Call) -> bool:
    return (isinstance(node.func, ast.Name) and node.func.id == "register_tool") or (
        isinstance(node.func, ast.Attribute) and node.func.attr == "register_tool"
    )


def _registered_tool_name(node: ast.Call) -> str | None:
    """Return the tool function name from a ``register_tool(mcp_instance,
    <fn>, ...)`` call, or ``None`` if *node* isn't such a call."""
    if _is_register_tool_call(node) and len(node.args) >= 2 and isinstance(node.args[1], ast.Name):
        return node.args[1].id
    return None


def _registered_tool_names_in_file(path: Path) -> set[str]:
    return {
        name
        for node in ast.walk(_parse(path))
        if isinstance(node, ast.Call) and (name := _registered_tool_name(node)) is not None
    }


def find_registered_tool_names(roots: tuple[Path, ...]) -> set[str]:
    """Return the set of distinct tool function names passed to
    ``register_tool(mcp_instance, <fn>, ...)`` anywhere under *roots*.

    tapps-mcp and docs-mcp register tools via ``mcp_register.register_tool``
    (TAP-1963), not a bare ``@mcp.tool()`` decorator -- verified against the
    real source before writing this. Deduplicated by name: several tools are
    registered from more than one server bundle module, but the definition
    -- not the registration call site -- is what costs context once per
    session.
    """
    names: set[str] = set()
    for root in roots:
        for path in root.rglob("*.py"):
            if path.name != _REGISTER_HELPER_NAME:
                names |= _registered_tool_names_in_file(path)
    return names


_ToolDefs = dict[str, tuple[Path, ast.FunctionDef | ast.AsyncFunctionDef]]


def _record_tool_definition(
    defs: _ToolDefs, name: str, path: Path, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> None:
    if name in defs:
        prior_path, _ = defs[name]
        raise MeasurementError(
            f"duplicate module-level definition for tool {name!r}: {prior_path} and {path}"
        )
    defs[name] = (path, node)


def _collect_tool_defs_in_file(path: Path, names: set[str], defs: _ToolDefs) -> None:
    for node in _parse(path).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            _record_tool_definition(defs, node.name, path, node)


def find_tool_definitions(roots: tuple[Path, ...], names: set[str]) -> _ToolDefs:
    """Map each registered tool name to its single module-level function
    definition. Raises if a name has zero or more than one definition --
    ambiguity here means the dedup contract this script depends on no
    longer holds, and guessing which definition is "the real one" would
    silently mismeasure the floor.
    """
    defs: _ToolDefs = {}
    for root in roots:
        for path in root.rglob("*.py"):
            _collect_tool_defs_in_file(path, names, defs)
    missing = names - set(defs)
    if missing:
        raise MeasurementError(f"no module-level definition found for tools: {sorted(missing)}")
    return defs


def _title_case_param(param_name: str) -> str:
    """Match FastMCP/pydantic's generated field title: snake_case -> Title Case."""
    return " ".join(word.capitalize() for word in param_name.split("_"))


def _split_optional(annotation: ast.expr) -> tuple[bool, ast.expr]:
    """Strip a top-level ``X | None`` union, returning (was_optional, X)."""
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        left, right = annotation.left, annotation.right
        if isinstance(right, ast.Constant) and right.value is None:
            return True, left
        if isinstance(left, ast.Constant) and left.value is None:
            return True, right
    return False, annotation


_SIMPLE_TYPE_MAP = {"str": "string", "bool": "boolean", "int": "integer", "float": "number"}


def _json_type_schema(annotation: ast.expr) -> dict[str, Any]:
    """Reconstruct the JSON Schema fragment pydantic emits for a bare
    (non-Optional) annotation. Verified byte-for-byte against a live
    ``mcp.server.fastmcp.FastMCP`` schema build for representative
    signatures (simple params, 37-param/6-Optional signature, required
    ``list[str]``) -- see the script's commit message / report for the
    exact cases checked.
    """
    if isinstance(annotation, ast.Name):
        mapped = _SIMPLE_TYPE_MAP.get(annotation.id)
        if mapped is None:
            raise MeasurementError(f"unhandled bare type annotation: {annotation.id}")
        return {"type": mapped}
    if isinstance(annotation, ast.Subscript) and isinstance(annotation.value, ast.Name):
        container = annotation.value.id
        if container == "list":
            return {"items": _json_type_schema(annotation.slice), "type": "array"}
        if container == "dict":
            return {"additionalProperties": True, "type": "object"}
        raise MeasurementError(f"unhandled subscript annotation: {ast.unparse(annotation)}")
    raise MeasurementError(f"unhandled annotation node: {ast.unparse(annotation)}")


def _is_context_param(annotation: ast.expr | None) -> bool:
    """FastMCP strips ``ctx: Context[...] | None`` params from the schema
    entirely (verified against a live FastMCP build); detect by annotation
    text rather than param name so a differently-named Context param is
    still excluded.
    """
    return annotation is not None and "Context" in ast.unparse(annotation)


def _optional_param_schema(
    base_annotation: ast.expr, default_node: ast.expr | None, has_default: bool, title: str
) -> dict[str, Any]:
    base_schema = _json_type_schema(base_annotation)
    default_value = ast.literal_eval(default_node) if has_default and default_node else None
    return {"anyOf": [base_schema, {"type": "null"}], "default": default_value, "title": title}


def _plain_param_schema(
    annotation: ast.expr, default_node: ast.expr | None, has_default: bool, title: str
) -> dict[str, Any]:
    prop = dict(_json_type_schema(annotation))
    if has_default and default_node is not None:
        prop["default"] = ast.literal_eval(default_node)
    prop["title"] = title
    return prop


def _add_param_to_schema(
    fn_name: str,
    arg: ast.arg,
    default_node: ast.expr | None,
    has_default: bool,
    properties: dict[str, Any],
    required: list[str],
) -> None:
    if arg.arg in ("self", "cls") or _is_context_param(arg.annotation):
        return
    if arg.annotation is None:
        raise MeasurementError(f"{fn_name}.{arg.arg}: missing type annotation")
    title = _title_case_param(arg.arg)
    is_optional, base_annotation = _split_optional(arg.annotation)
    if is_optional:
        prop = _optional_param_schema(base_annotation, default_node, has_default, title)
    else:
        prop = _plain_param_schema(arg.annotation, default_node, has_default, title)
    properties[arg.arg] = prop
    if not has_default:
        required.append(arg.arg)


def build_param_schema(
    fn_name: str, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> dict[str, Any]:
    """Reconstruct the ``inputSchema`` FastMCP/pydantic emits for *node*.

    Property key order does not affect the byte count this script cares
    about (same keys and values, just reordered), so this does not try to
    reproduce pydantic's exact key ordering -- only its exact key set and
    values.
    """
    args = node.args
    positional = args.posonlyargs + args.args
    n_no_default = len(positional) - len(args.defaults)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for i, arg in enumerate(positional):
        has_default = i >= n_no_default
        default_node = args.defaults[i - n_no_default] if has_default else None
        _add_param_to_schema(fn_name, arg, default_node, has_default, properties, required)

    for arg, default_node in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        _add_param_to_schema(
            fn_name, arg, default_node, default_node is not None, properties, required
        )

    schema: dict[str, Any] = {"properties": properties}
    if required:
        schema["required"] = required
    schema["title"] = f"{fn_name}Arguments"
    schema["type"] = "object"
    return schema


@dataclass
class ToolsResult:
    tool_count: int
    docstring_bytes: int
    param_bytes: int
    tools: list[ToolInfo]
    docstrings_over_400_bytes: int


def measure_tools(roots: tuple[Path, ...] = _TOOL_ROOTS) -> ToolsResult:
    names = find_registered_tool_names(roots)
    definitions = find_tool_definitions(roots, names)

    tools: list[ToolInfo] = []
    docstring_total = 0
    param_total = 0
    for name, (path, node) in definitions.items():
        docstring = ast.get_docstring(node) or ""
        docstring_bytes = len(docstring.encode("utf-8"))
        schema = build_param_schema(name, node)
        param_bytes = len(json.dumps(schema).encode("utf-8"))
        docstring_total += docstring_bytes
        param_total += param_bytes
        tools.append(
            ToolInfo(
                name=name,
                source_file=str(path.relative_to(_REPO_ROOT)),
                docstring_bytes=docstring_bytes,
                param_bytes=param_bytes,
            )
        )

    over_400 = sum(1 for tool in tools if tool.docstring_bytes > 400)
    return ToolsResult(
        tool_count=len(tools),
        docstring_bytes=docstring_total,
        param_bytes=param_total,
        tools=sorted(tools, key=lambda t: t.name),
        docstrings_over_400_bytes=over_400,
    )
