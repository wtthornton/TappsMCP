"""Static call resolution helpers for call graph indexing (TAP-4053)."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.project.call_graph_analyze import FileIndex


def qualify(
    idx: FileIndex,
    name: str,
    outer: list[str],
    *,
    class_name: str | None = None,
) -> str:
    parts = [idx.module, *outer]
    if class_name:
        parts.append(class_name)
    if name:
        parts.append(name)
    return ".".join(parts)


def unparse_expr(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<expr>"


def local_bindings(
    idx: FileIndex,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_stack: list[str],
) -> dict[str, str]:
    bindings = {a.arg: a.arg for a in node.args.args}
    for child in ast.walk(node):
        if not isinstance(child, ast.Assign):
            continue
        for target in child.targets:
            if not isinstance(target, ast.Name):
                continue
            if isinstance(child.value, ast.Name):
                bindings[target.id] = bindings.get(child.value.id, child.value.id)
            elif isinstance(child.value, ast.Call) and isinstance(child.value.func, ast.Name):
                resolved = resolve_name(idx, child.value.func.id, class_stack, bindings)
                if resolved:
                    bindings[target.id] = resolved
    return bindings


def resolve_name(
    idx: FileIndex,
    name: str,
    class_stack: list[str],
    bindings: dict[str, str],
) -> str | None:
    bound = bindings.get(name)
    if bound and bound != name and "." in bound:
        return bound
    if name in idx.functions:
        return idx.functions[name]
    methods = method_map(idx, class_stack)
    if name in methods:
        return methods[name]
    if name in idx.classes:
        return None
    if name in idx.imports:
        return idx.imports[name]
    for sym in idx.symbols:
        if sym.kind == "function" and sym.qualified_name.endswith(f".{name}"):
            return sym.qualified_name
    return None


def resolve_attribute(
    idx: FileIndex,
    node: ast.Attribute,
    class_stack: list[str],
    bindings: dict[str, str],
) -> str | None:
    attr = node.attr
    if isinstance(node.value, ast.Name):
        base = node.value.id
        if base in {"self", "cls"} and class_stack:
            return qualify(idx, attr, class_stack[:-1], class_name=class_stack[-1])
        if base in idx.classes:
            return f"{idx.classes[base]}.{attr}"
        if base in idx.imports:
            return f"{idx.imports[base]}.{attr}"
        bound = bindings.get(base)
        if bound and "." in bound:
            return f"{bound}.{attr}"
        return None
    if isinstance(node.value, ast.Attribute):
        inner = resolve_attribute(idx, node.value, class_stack, bindings)
        return f"{inner}.{attr}" if inner else None
    return None


def method_map(idx: FileIndex, class_stack: list[str]) -> dict[str, str]:
    if not class_stack:
        return {}
    prefix = ".".join([idx.module, *class_stack])
    return {
        sym.qualified_name.rsplit(".", maxsplit=1)[-1]: sym.qualified_name
        for sym in idx.symbols
        if sym.kind == "method" and sym.qualified_name.startswith(f"{prefix}.")
    }
