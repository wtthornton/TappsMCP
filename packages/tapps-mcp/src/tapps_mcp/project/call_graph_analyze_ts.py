"""Per-file tree-sitter analysis for TypeScript call graph indexing (TAP-4538).

S2 of the call-graph language expansion. Extracts function/method symbols and
static call edges from ``.ts``/``.tsx`` files, mirroring the Python analyzer in
``call_graph_analyze.py`` (two-phase: register symbols, then collect calls with
an explicit caller stack).

S3 (TAP-4539) adds v1 **cross-module** resolution via a lexical import-binding
table, mirroring the Python analyzer's ``resolve_name`` / ``resolve_attribute``
discipline in ``call_graph_resolve.py``. Resolved kinds: named imports, aliased
imports (de-aliased), namespace imports (``import * as U`` → ``U.greet()``),
plus the S2 in-module and intra-class ``this.method()`` cases. Everything else
(default imports, typed-receiver instance methods, re-exports, tsconfig path
aliases, external packages) becomes an honest ``ResolutionGap`` with a specific
reason — NEVER a guessed edge. Full default-export / path-alias / re-export
resolution is deferred to S4 (TAP-4540).

Deterministic contract (ADR-0004): no LLM, no network. When resolution is not
certain, emit a gap. Over-reaching resolution that fabricates an edge is the
failure mode this file is written to avoid.

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


def _resolve_relative_module(module: str, specifier: str) -> str | None:
    """Resolve a relative ES-module ``specifier`` against the importing ``module``.

    Modules are slash-delimited names produced by ``_ts_file_to_module`` (S1),
    e.g. ``a/b/consumer``. A specifier ``./util`` from ``a/b/consumer`` resolves
    to ``a/b/util``; ``../shared/x`` walks up one directory. Returns ``None``
    when the walk escapes above the module root (defensive — never guess).

    Non-relative specifiers (``fs``, ``lodash``, ``@/util``) are not handled
    here; the caller classifies those as external / path-alias gaps.
    """
    if not specifier.startswith("."):
        return None
    # Directory of the importing module (drop the file segment).
    base_parts = module.split("/")[:-1]
    spec_parts = specifier.split("/")
    for part in spec_parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not base_parts:
                return None  # escaped above root — do not fabricate a target.
            base_parts.pop()
            continue
        base_parts.append(part)
    if not base_parts:
        return None
    return "/".join(base_parts)


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
        # Cross-module import bindings (TAP-4539). Each maps a local binding name
        # to a resolution decision:
        #  - _named_bindings: local -> qualified callee ("<module>.<realName>"),
        #    a RESOLVABLE named/aliased import from an in-repo relative module.
        #  - _namespace_bindings: local alias -> target module ("import * as U").
        #  - _deferred_bindings: local -> gap reason for a binding we honestly
        #    cannot resolve yet (default export, external pkg, path alias).
        self._named_bindings: dict[str, str] = {}
        self._namespace_bindings: dict[str, str] = {}
        self._deferred_bindings: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Phase 0 — import binding table
    # ------------------------------------------------------------------

    def run(self, root: Any) -> None:
        for node in _iter_statements(root):
            self._scan_imports(node)
        for node in _iter_statements(root):
            self._register_top_level(node)
        # Phase 2 — collect calls per registered symbol body.
        for node in _iter_statements(root):
            self._collect_top_level(node)

    def _scan_imports(self, node: Any) -> None:
        """Record import/re-export bindings so phase 2 resolution is lexical.

        Mirrors ``call_graph_resolve._apply_import_bindings``: a binding maps a
        local name to a qualified target when it is a named/namespace import
        from an in-repo relative module, and to a deferred gap reason otherwise.
        """
        if node.type == "export_statement" and _is_reexport(node):
            # `export {x} from "./re"` — deferred to S4. Mark the point honestly.
            self.gaps.append(
                ResolutionGap(
                    self.module,
                    _node_text(node, self.source).strip(),
                    _line_of(node),
                    "reexport_unresolved",
                    language="typescript",
                )
            )
            return
        if node.type != "import_statement":
            return
        specifier = _import_specifier(node, self.source)
        if specifier is None:
            return
        clause = _first_child_of_type(node, "import_clause")
        if clause is None:
            return
        self._bind_import_clause(clause, specifier)

    def _bind_import_clause(self, clause: Any, specifier: str) -> None:
        target_module = _resolve_relative_module(self.module, specifier)
        is_relative = specifier.startswith(".")
        is_path_alias = _is_path_alias(specifier)
        for child in clause.children:
            if child.type == "named_imports":
                for local, real in _named_import_pairs(child, self.source):
                    if target_module is not None:
                        self._named_bindings[local] = f"{target_module}.{real}"
                    elif is_path_alias:
                        self._deferred_bindings[local] = "path_alias_unresolved"
                    else:  # external package (fs, lodash, ...)
                        self._deferred_bindings[local] = "import_unresolved"
            elif child.type == "namespace_import":
                alias = _namespace_alias(child, self.source)
                if not alias:
                    continue
                if target_module is not None:
                    self._namespace_bindings[alias] = target_module
                elif is_path_alias:
                    self._deferred_bindings[alias] = "path_alias_unresolved"
                else:
                    self._deferred_bindings[alias] = "import_unresolved"
            elif child.type == "identifier":
                # Default import: `import makeDefault from "./util"`.
                # Default-export resolution is deferred to S4 regardless of
                # whether the source module is in-repo — never guess.
                local = _node_text(child, self.source)
                if is_path_alias:
                    self._deferred_bindings[local] = "path_alias_unresolved"
                elif is_relative:
                    self._deferred_bindings[local] = "unresolved_default_export"
                else:
                    self._deferred_bindings[local] = "import_unresolved"

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
            self._gap(caller, _node_text(call, self.source), _line_of(call), "dynamic_dispatch")
            return
        expr = _node_text(func, self.source)
        line = _line_of(call)
        callee, reason = self._resolve(func, class_name)
        if callee is None:
            self._gap(caller, expr, line, reason)
            return
        self.edges.append(CallEdge(caller, callee, expr, line, True))

    def _gap(self, caller: str, expr: str, line: int, reason: str) -> None:
        self.gaps.append(ResolutionGap(caller, expr, line, reason, language="typescript"))

    def _resolve(self, func: Any, class_name: str | None) -> tuple[str | None, str]:
        """Resolve a call target to an in-repo symbol, or return (None, reason).

        Resolution order mirrors ``call_graph_resolve.resolve_name``: local
        module symbols first, then the lexical import-binding table. A binding
        we cannot follow yet yields its recorded deferred reason — never a
        guessed edge.
        """
        if func.type == "identifier":
            name = _node_text(func, self.source)
            qname = self._local_functions.get(name)
            if qname is not None:
                return qname, "unresolved_static_call"
            # Named / aliased import from an in-repo relative module (resolved).
            bound = self._named_bindings.get(name)
            if bound is not None:
                return bound, "unresolved_static_call"
            # A binding we deliberately did not resolve (default / external / alias).
            deferred = self._deferred_bindings.get(name)
            if deferred is not None:
                return None, deferred
            # A bare name we do not own and never saw imported.
            return None, "import_unresolved"
        if func.type == "member_expression":
            obj = func.child_by_field_name("object")
            prop = func.child_by_field_name("property")
            if obj is None or prop is None:
                return None, "unresolved_static_call"
            if obj.type == "this" and class_name:
                method_name = _node_text(prop, self.source)
                qname = self._class_methods.get(f"{class_name}.{method_name}")
                if qname is not None:
                    return qname, "unresolved_static_call"
                # this.<something not a known method> — dynamic within class.
                return None, "unresolved_static_call"
            if obj.type == "identifier":
                obj_name = _node_text(obj, self.source)
                # Namespace import: `import * as U from "./util"` -> U.greet().
                ns_module = self._namespace_bindings.get(obj_name)
                if ns_module is not None and prop.type == "property_identifier":
                    return f"{ns_module}.{_node_text(prop, self.source)}", "unresolved_static_call"
                # A namespace-like deferred binding (external `import * as fs`).
                deferred = self._deferred_bindings.get(obj_name)
                if deferred is not None:
                    return None, deferred
                # A local variable / typed receiver: `f.format()`. We cannot
                # know the receiver's type without a type checker — defer.
                return None, "receiver_untyped"
            # obj.method() where obj is not a plain identifier (chained, etc.).
            return None, "receiver_untyped"
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


def _first_child_of_type(node: Any, child_type: str) -> Any | None:
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _import_specifier(node: Any, source: bytes) -> str | None:
    """The module specifier string of an ``import_statement`` (unquoted)."""
    string_node = _first_child_of_type(node, "string")
    if string_node is None:
        return None
    frag = _first_child_of_type(string_node, "string_fragment")
    if frag is not None:
        return _node_text(frag, source)
    # Fallback: strip surrounding quotes from the raw string node.
    raw = _node_text(string_node, source)
    return raw.strip("\"'")


def _named_import_pairs(named_imports: Any, source: bytes) -> list[tuple[str, str]]:
    """Yield ``(local_name, real_name)`` for each ``import_specifier``.

    De-aliases ``{shout as loud}`` to ``("loud", "shout")``. A plain
    ``{greet}`` yields ``("greet", "greet")``.
    """
    out: list[tuple[str, str]] = []
    for spec in named_imports.children:
        if spec.type != "import_specifier":
            continue
        idents = [c for c in spec.children if c.type == "identifier"]
        if not idents:
            continue
        real = _node_text(idents[0], source)
        # `as` present -> the second identifier is the local binding name.
        local = _node_text(idents[1], source) if len(idents) >= 2 else real
        out.append((local, real))
    return out


def _namespace_alias(namespace_import: Any, source: bytes) -> str:
    """Local alias of ``import * as U`` -> ``"U"`` (last identifier child)."""
    idents = [c for c in namespace_import.children if c.type == "identifier"]
    return _node_text(idents[-1], source) if idents else ""


def _is_reexport(export_node: Any) -> bool:
    """True for ``export {x} from "..."`` (a re-export, not a local export)."""
    has_from = any(child.type == "from" for child in export_node.children)
    has_clause = any(child.type == "export_clause" for child in export_node.children)
    return has_from and has_clause


def _is_path_alias(specifier: str) -> bool:
    """True for a common tsconfig path alias (``@/util``, ``~/foo``).

    Conservative on purpose: only the ``@/`` and ``~/`` (and bare ``~``) sigils
    count. Scoped npm packages (``@angular/core``) start with ``@`` but are
    external, not aliases — misclassifying them would distort the gap taxonomy,
    so they fall through to the external ``import_unresolved`` branch.
    """
    return specifier.startswith(("@/", "~/")) or specifier == "~"
