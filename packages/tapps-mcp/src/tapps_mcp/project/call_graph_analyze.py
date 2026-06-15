"""Per-file AST analysis for call graph indexing (TAP-4053)."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tapps_mcp.project.call_graph_resolve import (
    local_bindings,
    qualify,
    resolve_attribute,
    resolve_name,
    unparse_expr,
)
from tapps_mcp.project.call_graph_types import CallEdge, ResolutionGap, SymbolKind, SymbolRecord


@dataclass
class FileIndex:
    module: str
    rel_path: str
    symbols: list[SymbolRecord] = field(default_factory=list)
    edges: list[CallEdge] = field(default_factory=list)
    gaps: list[ResolutionGap] = field(default_factory=list)
    classes: dict[str, str] = field(default_factory=dict)
    functions: dict[str, str] = field(default_factory=dict)
    imports: dict[str, str] = field(default_factory=dict)


def analyze_file(
    file_path: Path,
    module: str,
    project_root: Path,
) -> tuple[list[SymbolRecord], list[CallEdge], list[ResolutionGap]]:
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return [], [], []

    idx = FileIndex(module=module, rel_path=str(file_path.relative_to(project_root)))
    _load_imports(idx, tree)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            _register_class(idx, node, [])
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _register_symbol(idx, node, [], kind="function")
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            _scan_class_calls(idx, node, [])
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            _scan_function_calls(idx, node, qualify(idx, node.name, []), [])
    return idx.symbols, idx.edges, idx.gaps


def _load_imports(idx: FileIndex, tree: ast.Module) -> None:
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".", maxsplit=1)[0]
                idx.imports[bound] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                idx.imports[bound] = f"{base}.{alias.name}" if base else alias.name


def _register_class(idx: FileIndex, node: ast.ClassDef, outer: list[str]) -> None:
    stack = [*outer, node.name]
    idx.classes[node.name] = qualify(idx, node.name, outer)
    for item in node.body:
        if isinstance(item, ast.ClassDef):
            _register_class(idx, item, stack)
        elif isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            _register_symbol(idx, item, stack[:-1], class_name=stack[-1], kind="method")


def _register_symbol(
    idx: FileIndex,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    outer: list[str],
    *,
    class_name: str | None = None,
    kind: SymbolKind,
) -> None:
    qname = qualify(idx, node.name, outer, class_name=class_name)
    if kind == "function":
        idx.functions[node.name] = qname
    idx.symbols.append(SymbolRecord(qname, idx.module, idx.rel_path, node.lineno, kind))


def _scan_class_calls(idx: FileIndex, node: ast.ClassDef, outer: list[str]) -> None:
    stack = [*outer, node.name]
    for item in node.body:
        if isinstance(item, ast.ClassDef):
            _scan_class_calls(idx, item, stack)
        elif isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            caller = qualify(idx, item.name, stack[:-1], class_name=stack[-1])
            _scan_function_calls(idx, item, caller, stack)


def _scan_function_calls(
    idx: FileIndex,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    caller: str,
    class_stack: list[str],
) -> None:
    bindings = local_bindings(idx, node, class_stack)
    collector = _CallSiteCollector(
        on_call=lambda call_node: _record_call(idx, call_node, caller, class_stack, bindings)
    )
    for stmt in node.body:
        collector.visit(stmt)


def _record_call(
    idx: FileIndex,
    call_node: ast.Call,
    caller: str,
    class_stack: list[str],
    bindings: dict[str, str],
) -> None:
    expr = unparse_expr(call_node.func)
    callee: str | None
    if isinstance(call_node.func, ast.Name):
        callee = resolve_name(idx, call_node.func.id, class_stack, bindings)
    elif isinstance(call_node.func, ast.Attribute):
        callee = resolve_attribute(idx, call_node.func, class_stack, bindings)
    else:
        callee = None
    if callee is None:
        idx.gaps.append(ResolutionGap(caller, expr, call_node.lineno, "unresolved_static_call"))
        return
    idx.edges.append(CallEdge(caller, callee, expr, call_node.lineno, True))


class _CallSiteCollector(ast.NodeVisitor):
    def __init__(self, *, on_call: Callable[[ast.Call], None]) -> None:
        self._on_call = on_call
        self._stack: list[ast.AST] = []

    def visit(self, node: ast.AST) -> None:
        self._stack.append(node)
        super().visit(node)
        self._stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        parent = self._stack[-2] if len(self._stack) >= 2 else None
        if isinstance(parent, ast.Call) and parent.func is node:
            self.generic_visit(node)
            return
        self._on_call(node)
        self.generic_visit(node)
