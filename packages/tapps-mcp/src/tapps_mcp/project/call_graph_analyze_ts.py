"""Per-file tree-sitter analysis for TypeScript call graph indexing (TAP-4538).

S2 of the call-graph language expansion. Extracts function/method symbols and
static call edges from ``.ts``/``.tsx`` files, mirroring the Python analyzer in
``call_graph_analyze.py`` (two-phase: register symbols, then collect calls with
an explicit caller stack).

Deterministic contract (ADR-0004): no LLM, no network. A call that does not
resolve to an IN-MODULE symbol becomes a ``ResolutionGap`` — never a guessed
edge. Cross-module resolution is deferred to S3.

Graceful degradation: a missing ``tree_sitter`` / ``tree_sitter_typescript``
grammar yields an empty result (no crash); a genuine syntax error yields a
``ParseFailure`` rather than raising.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_mcp.project.call_graph_types import (
    CallEdge,
    ParseFailure,
    ResolutionGap,
    SymbolKind,
    SymbolRecord,
)

# Guard tree-sitter imports for graceful degradation (mirrors scorer_typescript).
_TS_LANGUAGE: Any = None
_TSX_LANGUAGE: Any = None
try:
    import tree_sitter
    import tree_sitter_typescript

    _TS_LANGUAGE = tree_sitter.Language(tree_sitter_typescript.language_typescript())
    _TSX_LANGUAGE = tree_sitter.Language(tree_sitter_typescript.language_tsx())
    HAS_TREE_SITTER = True
except ImportError:  # pragma: no cover - exercised only when grammar absent
    tree_sitter = None  # type: ignore[assignment]
    HAS_TREE_SITTER = False

# tree-sitter node types that carry a callable body we treat as a symbol.
_ARROW_TYPE = "arrow_function"
_METHOD_TYPE = "method_definition"
_FUNCTION_DECL_TYPE = "function_declaration"

AnalyzeResult = tuple[
    list[SymbolRecord],
    list[CallEdge],
    list[ResolutionGap],
    list[ParseFailure],
]


def analyze_file_ts(
    file_path: Path,
    module: str,
    project_root: Path,
) -> AnalyzeResult:
    """Extract TS symbols + call edges from ``file_path``.

    Same 4-tuple contract as ``call_graph_analyze.analyze_file``:
    ``(symbols, edges, resolution_gaps, parse_failures)``.
    """
    try:
        rel_path = str(file_path.relative_to(project_root))
    except ValueError:
        rel_path = str(file_path)

    if not HAS_TREE_SITTER:
        # No grammar available — degrade to empty, never crash.
        return [], [], [], []

    try:
        source_bytes = file_path.read_bytes()
    except OSError as exc:
        return [], [], [], [ParseFailure(rel_path, 0, f"io_error:{exc.__class__.__name__}")]

    try:
        source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return [], [], [], [ParseFailure(rel_path, 0, "decode_error")]

    lang = _TSX_LANGUAGE if file_path.suffix.lower() == ".tsx" else _TS_LANGUAGE
    try:
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(source_bytes)
    except Exception:  # pragma: no cover - defensive; parse rarely raises
        return [], [], [], [ParseFailure(rel_path, 0, "syntax_error")]

    root = tree.root_node
    if root.has_error:
        line = (root.start_point[0] + 1) if root.start_point else 0
        return [], [], [], [ParseFailure(rel_path, line, "syntax_error")]

    analyzer = _TsFileAnalyzer(module=module, rel_path=rel_path, source=source_bytes)
    analyzer.run(root)
    return analyzer.symbols, analyzer.edges, analyzer.gaps, []


def _node_text(node: Any, source: bytes) -> str:
    """Decode a node's source span (mirrors treesitter_base helper)."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _line_of(node: Any) -> int:
    """1-based line number of a node."""
    return int(node.start_point[0]) + 1


class _TsFileAnalyzer:
    """Two-phase TS analyzer: register symbols, then collect calls.

    Phase 1 registers every top-level ``function``, arrow-function ``const``,
    and class method into ``self._local_functions`` (bare name -> qualified
    name) and ``self._class_methods`` (``ClassName.method`` -> qualified name).
    Phase 2 walks each symbol body with an explicit caller, emitting a
    ``CallEdge`` only when a call resolves to one of those in-module symbols.
    """

    def __init__(self, *, module: str, rel_path: str, source: bytes) -> None:
        self.module = module
        self.rel_path = rel_path
        self.source = source
        self.symbols: list[SymbolRecord] = []
        self.edges: list[CallEdge] = []
        self.gaps: list[ResolutionGap] = []
        # Bare function name -> qualified name (module-scoped functions/arrows).
        self._local_functions: dict[str, str] = {}
        # "ClassName.method" -> qualified name.
        self._class_methods: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Phase 1 — symbol registration
    # ------------------------------------------------------------------

    def run(self, root: Any) -> None:
        for node in _iter_statements(root):
            self._register_top_level(node)
        # Phase 2 — collect calls per registered symbol body.
        for node in _iter_statements(root):
            self._collect_top_level(node)

    def _register_top_level(self, node: Any) -> None:
        node = _unwrap_export(node)
        if node is None:
            return
        if node.type == _FUNCTION_DECL_TYPE:
            name = self._decl_name(node)
            if name:
                qname = self._qualify(name)
                self._local_functions[name] = qname
                self.symbols.append(self._symbol(qname, node, "function"))
        elif node.type == "lexical_declaration":
            for name, arrow in _arrow_declarators(node, self.source):
                qname = self._qualify(name)
                self._local_functions[name] = qname
                self.symbols.append(self._symbol(qname, arrow, "function"))
        elif node.type == "class_declaration":
            self._register_class(node)

    def _register_class(self, node: Any) -> None:
        class_name = self._decl_name(node, field="name")
        if not class_name:
            # Fall back to the type_identifier child.
            class_name = _first_child_text(node, "type_identifier", self.source)
        if not class_name:
            return
        body = node.child_by_field_name("body")
        if body is None:
            return
        for member in body.children:
            if member.type != _METHOD_TYPE:
                continue
            method_name = _first_child_text(member, "property_identifier", self.source)
            if not method_name:
                continue
            qname = self._qualify_method(class_name, method_name)
            self._class_methods[f"{class_name}.{method_name}"] = qname
            self.symbols.append(self._symbol(qname, member, "method"))

    # ------------------------------------------------------------------
    # Phase 2 — call collection
    # ------------------------------------------------------------------

    def _collect_top_level(self, node: Any) -> None:
        node = _unwrap_export(node)
        if node is None:
            return
        if node.type == _FUNCTION_DECL_TYPE:
            name = self._decl_name(node)
            if name:
                self._collect_calls(node, caller=self._qualify(name), class_name=None)
        elif node.type == "lexical_declaration":
            for name, arrow in _arrow_declarators(node, self.source):
                self._collect_calls(arrow, caller=self._qualify(name), class_name=None)
        elif node.type == "class_declaration":
            class_name = self._decl_name(node, field="name") or _first_child_text(
                node, "type_identifier", self.source
            )
            body = node.child_by_field_name("body")
            if not class_name or body is None:
                return
            for member in body.children:
                if member.type != _METHOD_TYPE:
                    continue
                method_name = _first_child_text(member, "property_identifier", self.source)
                if not method_name:
                    continue
                self._collect_calls(
                    member,
                    caller=self._qualify_method(class_name, method_name),
                    class_name=class_name,
                )

    def _collect_calls(self, body: Any, *, caller: str, class_name: str | None) -> None:
        """Walk ``body`` for ``call_expression`` sites, attributing each to ``caller``.

        Nested function/arrow/method bodies re-root the caller (a call inside a
        nested closure is attributed to that closure), mirroring the Python
        analyzer's per-symbol caller discipline. Calls that are only inside a
        ``const x = f()`` initializer still attribute to the enclosing ``caller``
        because the variable declarator is not a callable body.
        """
        for call in self._walk_calls(body, skip_root=True):
            self._record_call(call, caller=caller, class_name=class_name)

    def _walk_calls(self, node: Any, *, skip_root: bool) -> list[Any]:
        """Collect ``call_expression`` nodes owned by ``node``'s body.

        Descends through non-callable containers — crucially including
        ``variable_declarator`` — so a call in ``const x = f()`` is attributed
        to the enclosing symbol (AC3). It does NOT descend into a nested
        callable body (arrow / function / method): those are either their own
        registered symbol (re-walked in phase 2) or an anonymous inline closure,
        whose calls are deliberately dropped here rather than mis-attributed to
        the enclosing caller (deterministic contract — never guess a caller).
        """
        out: list[Any] = []
        for child in node.children:
            if not skip_root and child.type == "call_expression":
                out.append(child)
            if child.type in (_ARROW_TYPE, _FUNCTION_DECL_TYPE, "function_expression"):
                continue
            if child.type == _METHOD_TYPE:
                continue
            out.extend(self._walk_calls(child, skip_root=False))
        return out

    def _record_call(self, call: Any, *, caller: str, class_name: str | None) -> None:
        func = call.child_by_field_name("function")
        if func is None:
            self.gaps.append(
                ResolutionGap(caller, _node_text(call, self.source), _line_of(call), "dynamic_dispatch")
            )
            return
        expr = _node_text(func, self.source)
        line = _line_of(call)
        callee, reason = self._resolve(func, class_name)
        if callee is None:
            self.gaps.append(ResolutionGap(caller, expr, line, reason))
            return
        self.edges.append(CallEdge(caller, callee, expr, line, True))

    def _resolve(self, func: Any, class_name: str | None) -> tuple[str | None, str]:
        """Resolve a call target to an in-module symbol, or return (None, reason)."""
        if func.type == "identifier":
            name = _node_text(func, self.source)
            qname = self._local_functions.get(name)
            if qname is not None:
                return qname, "unresolved_static_call"
            # A bare name we do not own: could be an import or builtin.
            return None, "import_unresolved"
        if func.type == "member_expression":
            obj = func.child_by_field_name("object")
            prop = func.child_by_field_name("property")
            if obj is not None and prop is not None and obj.type == "this" and class_name:
                method_name = _node_text(prop, self.source)
                qname = self._class_methods.get(f"{class_name}.{method_name}")
                if qname is not None:
                    return qname, "unresolved_static_call"
                # this.<something not a known method> — dynamic within class.
                return None, "unresolved_static_call"
            # obj.method() across a module boundary or external object.
            return None, "unresolved_static_call"
        # call().foo(), (expr)(), tagged templates, etc.
        return None, "dynamic_dispatch"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _qualify(self, name: str) -> str:
        return f"{self.module}.{name}"

    def _qualify_method(self, class_name: str, method_name: str) -> str:
        return f"{self.module}.{class_name}.{method_name}"

    def _symbol(self, qname: str, node: Any, kind: SymbolKind) -> SymbolRecord:
        return SymbolRecord(
            qualified_name=qname,
            module=self.module,
            file_path=self.rel_path,
            line=_line_of(node),
            kind=kind,
            language="typescript",
        )

    def _decl_name(self, node: Any, *, field: str = "name") -> str:
        name_node = node.child_by_field_name(field)
        if name_node is not None:
            return _node_text(name_node, self.source)
        return ""


# ----------------------------------------------------------------------
# Module-level tree helpers
# ----------------------------------------------------------------------


def _iter_statements(root: Any) -> list[Any]:
    """Top-level statements of a ``program`` node."""
    return list(root.children)


def _unwrap_export(node: Any) -> Any | None:
    """Return the declaration wrapped by an ``export_statement``, or the node itself."""
    if node.type == "export_statement":
        for child in node.children:
            if child.type in (
                _FUNCTION_DECL_TYPE,
                "lexical_declaration",
                "class_declaration",
            ):
                return child
        return None
    if node.type in (_FUNCTION_DECL_TYPE, "lexical_declaration", "class_declaration"):
        return node
    return None


def _arrow_declarators(lexical: Any, source: bytes) -> list[tuple[str, Any]]:
    """Yield ``(name, arrow_function_node)`` for ``const x = () => ...`` declarators."""
    out: list[tuple[str, Any]] = []
    for declarator in lexical.children:
        if declarator.type != "variable_declarator":
            continue
        name_node = declarator.child_by_field_name("name")
        value_node = declarator.child_by_field_name("value")
        if name_node is None or value_node is None:
            continue
        if value_node.type != _ARROW_TYPE:
            continue
        if name_node.type != "identifier":
            continue
        out.append((_node_text(name_node, source), value_node))
    return out


def _first_child_text(node: Any, child_type: str, source: bytes) -> str:
    for child in node.children:
        if child.type == child_type:
            return _node_text(child, source)
    return ""
