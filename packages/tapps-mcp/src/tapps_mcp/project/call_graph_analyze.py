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
from tapps_mcp.project.call_graph_types import (
    CallEdge,
    ParseFailure,
    ResolutionGap,
    SymbolKind,
    SymbolRecord,
)

_FRAMEWORK_DECORATOR_SUFFIXES = (
    ".get",
    ".post",
    ".put",
    ".patch",
    ".delete",
    ".route",
    ".tool",
    ".command",
    ".group",
)


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
) -> tuple[list[SymbolRecord], list[CallEdge], list[ResolutionGap], list[ParseFailure]]:
    rel_path = str(file_path.relative_to(project_root))
    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [], [], [ParseFailure(rel_path, 0, f"io_error:{exc.__class__.__name__}")]

    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        return [], [], [], [ParseFailure(rel_path, exc.lineno or 0, "syntax_error")]
    except UnicodeDecodeError:
        return [], [], [], [ParseFailure(rel_path, 0, "decode_error")]

    idx = FileIndex(module=module, rel_path=rel_path)
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
            _scan_framework_routes(idx, node, qualify(idx, node.name, []))
    return idx.symbols, idx.edges, idx.gaps, []


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
            _scan_framework_routes(idx, item, caller)


def _scan_function_calls(
    idx: FileIndex,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    caller: str,
    class_stack: list[str],
) -> None:
    bindings = local_bindings(idx, node, class_stack)
    collector = _CallSiteCollector(
        on_call=lambda call_node, active_caller: _record_call(
            idx, call_node, active_caller, class_stack, bindings
        ),
        caller=caller,
    )
    for stmt in node.body:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            nested = f"{caller}.{stmt.name}"
            idx.symbols.append(
                SymbolRecord(nested, idx.module, idx.rel_path, stmt.lineno, "function")
            )
            _scan_function_calls(idx, stmt, nested, class_stack)
            _scan_framework_routes(idx, stmt, nested)
        collector.visit(stmt)


def _scan_framework_routes(
    idx: FileIndex,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    handler: str,
) -> None:
    """Bounded FastAPI/Click/MCP route entry edges (TAP-4094)."""
    for dec in node.decorator_list:
        expr = unparse_expr(dec)
        lowered = expr.lower()
        if not any(token in lowered for token in _FRAMEWORK_DECORATOR_SUFFIXES):
            continue
        if not any(
            hint in lowered
            for hint in ("click", "router", "app.", "mcp", "fastapi", "route", "command", "tool")
        ):
            continue
        route_caller = f"route:{idx.module}:{expr}"
        idx.edges.append(CallEdge(route_caller, handler, expr, node.lineno, True))


def _record_call(
    idx: FileIndex,
    call_node: ast.Call,
    caller: str,
    class_stack: list[str],
    bindings: dict[str, str],
) -> None:
    expr = unparse_expr(call_node.func)
    callee: str | None
    reason = "unresolved_static_call"
    if isinstance(call_node.func, ast.Name):
        callee = resolve_name(idx, call_node.func.id, class_stack, bindings)
    elif isinstance(call_node.func, ast.Attribute):
        callee = resolve_attribute(idx, call_node.func, class_stack, bindings)
        if callee is None and call_node.func.attr in {"apply", "map", "filter", "reduce"}:
            reason = "framework_hof"
    else:
        callee = None
        if isinstance(call_node.func, ast.Lambda):
            reason = "callback_opaque"
        else:
            reason = "dynamic_dispatch"
    if callee is None:
        idx.gaps.append(ResolutionGap(caller, expr, call_node.lineno, reason))
        return
    idx.edges.append(CallEdge(caller, callee, expr, call_node.lineno, True))


class _CallSiteCollector(ast.NodeVisitor):
    def __init__(
        self,
        *,
        on_call: Callable[[ast.Call, str], None],
        caller: str,
    ) -> None:
        self._on_call = on_call
        self._caller = caller
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
        self._on_call(node, self._caller)
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        lambda_caller = f"{self._caller}:lambda:{node.lineno}"
        inner = _CallSiteCollector(on_call=self._on_call, caller=lambda_caller)
        inner.visit(node.body)
