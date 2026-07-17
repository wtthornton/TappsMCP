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


def _apply_import_bindings(
    idx: FileIndex,
    bindings: dict[str, str],
    node: ast.Import | ast.ImportFrom,
) -> None:
    """Record Import/ImportFrom bindings (module-level or in-function lazy imports)."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            bound = alias.asname or alias.name.split(".", maxsplit=1)[0]
            bindings[bound] = alias.name
        return
    base = node.module or ""
    for alias in node.names:
        if alias.name == "*":
            continue
        bound = alias.asname or alias.name
        bindings[bound] = f"{base}.{alias.name}" if base else alias.name


def _annotation_target(idx: FileIndex, ann: ast.expr | None) -> str | None:
    """Qualified class an annotation names, resolved via local classes / imports.

    Conservative on purpose: only a bare ``Name`` (``x: Worker``), a dotted
    ``Attribute`` (``x: mod.Worker``), or a string forward-ref (``x: "Worker"``).
    Subscripted / union annotations (``Optional[Worker]``, ``list[Worker]``,
    ``A | B``) are skipped — their runtime type is not a single obvious class, so
    binding one would risk a wrong edge. Returns None unless the head resolves to
    a known local class or an imported name (mirrors how ``x = Worker()`` binds).
    """
    name: str | None = None
    if isinstance(ann, ast.Name):
        name = ann.id
    elif isinstance(ann, ast.Attribute):
        unparsed = unparse_expr(ann)
        name = unparsed if all(p.isidentifier() for p in unparsed.split(".")) else None
    elif isinstance(ann, ast.Constant) and isinstance(ann.value, str):
        candidate = ann.value.strip()
        name = candidate if candidate and all(
            p.isidentifier() for p in candidate.split(".")
        ) else None
    if not name:
        return None
    head, _, rest = name.partition(".")
    if head in idx.classes:
        base = idx.classes[head]
    elif head in idx.imports:
        base = idx.imports[head]
    else:
        return None
    result = f"{base}.{rest}" if rest else base
    return result


def local_bindings(
    idx: FileIndex,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_stack: list[str],
) -> dict[str, str]:
    # Seed parameter bindings, resolving type annotations to their class so that
    # ``def f(x: Worker): x.method()`` resolves the same as ``x = Worker()``.
    bindings: dict[str, str] = {}
    for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
        bindings[arg.arg] = _annotation_target(idx, arg.annotation) or arg.arg
    for child in ast.walk(node):
        if isinstance(child, ast.Import | ast.ImportFrom):
            _apply_import_bindings(idx, bindings, child)
            continue
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            # Annotated local: ``w: Worker`` / ``w: Worker = factory()``.
            annotated = _annotation_target(idx, child.annotation)
            if annotated:
                bindings[child.target.id] = annotated
            continue
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
