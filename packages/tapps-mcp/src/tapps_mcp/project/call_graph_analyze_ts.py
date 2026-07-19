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
(typed-receiver instance methods, external packages) becomes an honest
``ResolutionGap`` with a specific reason — NEVER a guessed edge.

S4 (TAP-4540) resolves the three previously-deferred classes — default exports,
tsconfig path aliases, and re-exports — via a **cross-file post-pass** in
``call_graph.build_call_graph_index``. The per-file analyzer still cannot see
other modules' export tables, so it records each of those as a ``DeferredCall``
(the gap it *would* emit plus structured hints: import kind, imported name,
target module, raw specifier) and exposes each module's ``ModuleExports``
(default symbol, named exports, re-export map). The post-pass promotes a
``DeferredCall`` to an edge when the origin symbol is found, and follows
re-export chains; anything still unresolved keeps its honest gap.

Deterministic contract (ADR-0004): no LLM, no network. When resolution is not
certain, emit a gap. Over-reaching resolution that fabricates an edge is the
failure mode this file is written to avoid.

Graceful degradation: a missing ``tree_sitter`` / ``tree_sitter_typescript``
grammar yields an empty result (no crash); a genuine syntax error yields a
``ParseFailure`` rather than raising.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tapps_mcp.project.call_graph_types import (
    CallEdge,
    DeferredCall,
    DeferredImportKind,
    ModuleExports,
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


@dataclass
class _DeferredMeta:
    """Structured hints for a deferred import binding (TAP-4540, per-file).

    Recorded only for the classes the S4 post-pass can *potentially* resolve
    (default export, path alias). ``target_module`` is set when the specifier is
    a resolvable relative module; ``None`` when it is a path alias awaiting
    tsconfig resolution against the raw ``specifier``.
    """

    kind: DeferredImportKind
    imported_name: str | None
    target_module: str | None
    specifier: str


AnalyzeResult = tuple[
    list[SymbolRecord],
    list[CallEdge],
    list[ResolutionGap],
    list[ParseFailure],
]

# Full result (TAP-4540): the 4-tuple plus the module's export surface and the
# deferred call sites the cross-file post-pass must try to resolve.
AnalyzeResultFull = tuple[
    list[SymbolRecord],
    list[CallEdge],
    list[ResolutionGap],
    list[ParseFailure],
    ModuleExports,
    list[DeferredCall],
]


def analyze_file_ts(
    file_path: Path,
    module: str,
    project_root: Path,
) -> AnalyzeResult:
    """Extract TS symbols + call edges from ``file_path``.

    Same 4-tuple contract as ``call_graph_analyze.analyze_file``:
    ``(symbols, edges, resolution_gaps, parse_failures)``.

    Standalone (no cross-file context), the deferred-resolution cases (default
    export / path alias) have no origin module to resolve against, so their
    ``DeferredCall`` records are folded back into honest gaps here — the 4-tuple
    API keeps the S3 contract. Re-exports are a module-level export fact (not a
    call site) and produce a ``reexport_unresolved`` gap only in this standalone
    view; the cross-file promotion happens in ``analyze_file_ts_full`` + the
    post-pass, which consumes the export table instead.
    """
    analyzer, failure = _parse_and_run(file_path, module, project_root)
    if analyzer is None:
        return [], [], [], ([] if failure is None else [failure])
    folded = list(analyzer.gaps)
    folded.extend(dc.gap for dc in analyzer.deferred_calls)
    folded.extend(analyzer.reexport_gaps)
    return analyzer.symbols, analyzer.edges, folded, []


def analyze_file_ts_full(
    file_path: Path,
    module: str,
    project_root: Path,
) -> AnalyzeResultFull:
    """Like ``analyze_file_ts`` but also returns cross-file resolution material.

    Adds ``ModuleExports`` (default symbol, named exports, re-export map) and the
    list of ``DeferredCall`` records for calls the per-file pass could not
    resolve alone. On any parse/IO failure the exports are empty and there are
    no deferred calls — the post-pass simply has nothing to promote.

    The returned ``gaps`` list holds only the genuinely-unresolvable-anywhere
    cases (untyped receiver, external import, dynamic dispatch). Deferred call
    gaps and re-export gaps are NOT in it: the cross-file post-pass owns those
    (a re-export statement with no consumer produces no gap; a consumer call
    through a broken chain produces its own deferred gap).
    """
    analyzer, failure = _parse_and_run(file_path, module, project_root)
    if analyzer is None:
        empty_exports = ModuleExports(module=module)
        return [], [], [], ([] if failure is None else [failure]), empty_exports, []
    return (
        analyzer.symbols,
        analyzer.edges,
        analyzer.gaps,
        [],
        analyzer.exports,
        analyzer.deferred_calls,
    )


def _parse_and_run(
    file_path: Path,
    module: str,
    project_root: Path,
) -> tuple[_TsFileAnalyzer | None, ParseFailure | None]:
    """Parse ``file_path`` and run the two-phase analyzer.

    Returns ``(analyzer, None)`` on success, ``(None, failure)`` on a parse/IO
    error, or ``(None, None)`` when the grammar is unavailable (degrade empty).
    """
    try:
        rel_path = str(file_path.relative_to(project_root))
    except ValueError:
        rel_path = str(file_path)

    if not HAS_TREE_SITTER:
        return None, None

    try:
        source_bytes = file_path.read_bytes()
    except OSError as exc:
        return None, ParseFailure(rel_path, 0, f"io_error:{exc.__class__.__name__}")

    try:
        source_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return None, ParseFailure(rel_path, 0, "decode_error")

    lang = _TSX_LANGUAGE if file_path.suffix.lower() == ".tsx" else _TS_LANGUAGE
    try:
        parser = tree_sitter.Parser(lang)
        tree = parser.parse(source_bytes)
    except Exception:  # pragma: no cover - defensive; parse rarely raises
        return None, ParseFailure(rel_path, 0, "syntax_error")

    root = tree.root_node
    if root.has_error:
        line = (root.start_point[0] + 1) if root.start_point else 0
        return None, ParseFailure(rel_path, line, "syntax_error")

    analyzer = _TsFileAnalyzer(module=module, rel_path=rel_path, source=source_bytes)
    analyzer.run(root)
    return analyzer, None


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
        # Cross-file resolution material (TAP-4540).
        self.exports = ModuleExports(module=module)
        self.deferred_calls: list[DeferredCall] = []
        # Standalone-view re-export gaps: what the 4-tuple ``analyze_file_ts``
        # reports for `export ... from` statements when there is no cross-file
        # context to follow the chain. The post-pass ignores these (it uses the
        # export table instead).
        self.reexport_gaps: list[ResolutionGap] = []
        # Bare function name -> qualified name (module-scoped functions/arrows).
        self._local_functions: dict[str, str] = {}
        # "ClassName.method" -> qualified name.
        self._class_methods: dict[str, str] = {}
        # tree-sitter node ids of the callable bodies that ARE registered
        # symbols (top-level function decls, top-level arrow-const values, class
        # methods). Phase 2 re-walks each of these as its own caller, so
        # ``_walk_calls`` must STOP at them. Any *other* nested callable body —
        # an anonymous arrow/function-expression closure (e.g. the callback in
        # ``items.forEach(x => helper())``) — is NOT in this set, so the walk
        # descends through it and attributes its calls to the nearest enclosing
        # named symbol (TAP-4552), never dropping or mis-attributing them.
        self._symbol_bodies: set[int] = set()
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
        # Deferred-binding metadata for the S4 cross-file post-pass (TAP-4540):
        # local binding name -> (kind, imported_name|None, target_module|None,
        # specifier). Only populated for the resolvable-later classes (default
        # export, path alias); external imports get no metadata (stay gaps).
        self._deferred_meta: dict[str, _DeferredMeta] = {}

    # ------------------------------------------------------------------
    # Phase 0 — import binding table
    # ------------------------------------------------------------------

    def run(self, root: Any) -> None:
        for node in _iter_statements(root):
            self._scan_imports(node)
        for node in _iter_statements(root):
            self._register_top_level(node)
        for node in _iter_statements(root):
            self._register_exports(node)
        # Phase 2 — collect calls per registered symbol body.
        for node in _iter_statements(root):
            self._collect_top_level(node)

    def _scan_imports(self, node: Any) -> None:
        """Record import/re-export bindings so phase 2 resolution is lexical.

        Mirrors ``call_graph_resolve._apply_import_bindings``: a binding maps a
        local name to a qualified target when it is a named/namespace import
        from an in-repo relative module, and to a deferred gap reason otherwise.

        Re-export statements (``export {x} from "./y"``, ``export * from "./y"``)
        are recorded in the module's re-export table (TAP-4540) so the post-pass
        can follow the chain to the origin symbol — no longer an unconditional
        gap.
        """
        if node.type == "export_statement" and _is_reexport(node):
            self._record_reexport(node)
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
                        # Path-alias named import — resolvable later via tsconfig.
                        self._deferred_bindings[local] = "path_alias_unresolved"
                        self._deferred_meta[local] = _DeferredMeta("named", real, None, specifier)
                    else:  # external package (fs, lodash, ...)
                        self._deferred_bindings[local] = "import_unresolved"
            elif child.type == "namespace_import":
                alias = _namespace_alias(child, self.source)
                if not alias:
                    continue
                if target_module is not None:
                    self._namespace_bindings[alias] = target_module
                elif is_path_alias:
                    # Path-alias namespace import — the accessed member name is
                    # known only at the call site, so imported_name stays None
                    # here and is filled in when the deferred call is recorded.
                    self._deferred_bindings[alias] = "path_alias_unresolved"
                    self._deferred_meta[alias] = _DeferredMeta("namespace", None, None, specifier)
                else:
                    self._deferred_bindings[alias] = "import_unresolved"
            elif child.type == "identifier":
                # Default import: `import makeDefault from "./util"`.
                # Default-export resolution needs the target module's default
                # symbol, which the per-file pass cannot see — defer to S4.
                local = _node_text(child, self.source)
                if is_path_alias:
                    self._deferred_bindings[local] = "path_alias_unresolved"
                    self._deferred_meta[local] = _DeferredMeta("default", None, None, specifier)
                elif is_relative:
                    self._deferred_bindings[local] = "unresolved_default_export"
                    self._deferred_meta[local] = _DeferredMeta(
                        "default", None, target_module, specifier
                    )
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
                self._symbol_bodies.add(id(node))
                self.symbols.append(self._symbol(qname, node, "function"))
        elif node.type == "lexical_declaration":
            for name, arrow in _arrow_declarators(node, self.source):
                qname = self._qualify(name)
                self._local_functions[name] = qname
                self._symbol_bodies.add(id(arrow))
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
            self._symbol_bodies.add(id(member))
            self.symbols.append(self._symbol(qname, member, "method"))

    # ------------------------------------------------------------------
    # Phase 1b — export surface (TAP-4540)
    # ------------------------------------------------------------------

    def _register_exports(self, node: Any) -> None:
        """Record this module's export surface for cross-file resolution.

        Sets ``exports.default_symbol`` (the ``export default`` target's
        qualified name, when it names an in-module symbol) and records local
        alias exports (``export { impl as pub }``) in the re-export table so the
        post-pass can follow ``pub`` back to the local symbol. Plain
        ``export function f`` needs no bookkeeping — the symbol is already in the
        global symbol table under its own qualified name. Re-export ``from``
        statements are handled in ``_scan_imports`` -> ``_record_reexport``.
        """
        if node.type != "export_statement":
            return
        if _is_reexport(node):
            return  # handled during import scan
        # `export default <name|decl>`
        if _has_default_keyword(node):
            self._register_default_export(node)
            return
        # `export { impl as pub }` (local export clause, no `from`): a rename
        # means consumers import `pub`, but the symbol is registered as `impl`.
        clause = _first_child_of_type(node, "export_clause")
        if clause is not None:
            for local, exported in _export_clause_pairs(clause, self.source):
                if exported != local and local in self._local_functions:
                    # Empty specifier == "origin is in this same module".
                    self.exports.reexports[exported] = ("", local)

    def _register_default_export(self, node: Any) -> None:
        """Resolve ``export default <target>`` to a qualified in-module symbol."""
        # `export default function foo() {}` / `export default class C {}`
        for child in node.children:
            if child.type in (_FUNCTION_DECL_TYPE, "class_declaration"):
                name = self._decl_name(child, field="name") or _first_child_text(
                    child, "type_identifier", self.source
                )
                if name:
                    self.exports.default_symbol = self._qualify(name)
                return
        # `export default foo;` — a bare identifier naming a local symbol.
        for child in node.children:
            if child.type == "identifier":
                name = _node_text(child, self.source)
                qname = self._local_functions.get(name)
                if qname is not None:
                    self.exports.default_symbol = qname
                return
        # `export default () => {}` / `export default { ... }` — anonymous, no
        # nameable symbol. Leave default_symbol None (post-pass keeps the gap).

    def _record_reexport(self, node: Any) -> None:
        """Record a ``... from "./y"`` re-export in the module's export table.

        ``export { a as b } from "./y"`` -> reexports["b"] = ("./y", "a").
        ``export * from "./y"`` -> star_reexports.append("./y").
        """
        specifier = _import_specifier(node, self.source)
        if specifier is None:
            return
        # Standalone-view gap (unchanged from S3): honest until the post-pass
        # follows the chain.
        self.reexport_gaps.append(
            ResolutionGap(
                self.module,
                _node_text(node, self.source).strip(),
                _line_of(node),
                "reexport_unresolved",
                language="typescript",
            )
        )
        clause = _first_child_of_type(node, "export_clause")
        if clause is not None:
            for local, exported in _export_clause_pairs(clause, self.source):
                # For a re-export, ``local`` is the origin name in the source
                # module and ``exported`` is what this module re-exports as.
                self.exports.reexports[exported] = (specifier, local)
            return
        # `export * from "./y"` — no clause; a namespace/star re-export.
        if any(child.type == "*" for child in node.children):
            self.exports.star_reexports.append(specifier)

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
        """Collect ``call_expression`` nodes attributed to ``node``'s symbol.

        Descends through non-callable containers — crucially including
        ``variable_declarator`` — so a call in ``const x = f()`` is attributed
        to the enclosing symbol (AC3).

        Nested callable bodies split two ways (TAP-4552):

        * A callable that IS a registered symbol (a top-level function decl,
          top-level arrow-const, or class method — tracked in
          ``self._symbol_bodies``) is its own scope and is re-walked in phase 2
          as its own caller, so the walk STOPS at it here to avoid
          double-attribution.
        * An ANONYMOUS closure (arrow / function-expression not registered as a
          symbol — e.g. ``x => helper()`` in ``items.forEach(x => helper())``)
          has no symbol of its own. The walk DESCENDS through it so its calls
          attribute to the nearest enclosing NAMED symbol. Previously these
          calls were dropped; now they are attributed correctly. Resolution of
          the recovered call is identical to a direct call (``_resolve``), so an
          unresolved callee still becomes an honest gap — never a guess.
        """
        out: list[Any] = []
        for child in node.children:
            if not skip_root and child.type == "call_expression":
                out.append(child)
            if child.type in (
                _ARROW_TYPE,
                _FUNCTION_DECL_TYPE,
                "function_expression",
                _METHOD_TYPE,
            ):
                # Stop only at a registered symbol body (its own scope); descend
                # through an anonymous closure to attribute its calls upward.
                if id(child) in self._symbol_bodies:
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
        callee, reason, deferred_key, member = self._resolve(func, class_name)
        if callee is not None:
            self.edges.append(CallEdge(caller, callee, expr, line, True))
            return
        gap = ResolutionGap(caller, expr, line, reason, language="typescript")
        # A deferrable binding (default export / path alias) — hand the gap to
        # the S4 cross-file post-pass with the structured hints it needs. If the
        # post-pass cannot resolve it either, it emits this same gap unchanged.
        meta = self._deferred_meta.get(deferred_key) if deferred_key else None
        if meta is not None:
            imported = member if meta.kind == "namespace" else meta.imported_name
            self.deferred_calls.append(
                DeferredCall(
                    gap=gap,
                    kind=meta.kind,
                    imported_name=imported,
                    target_module=meta.target_module,
                    specifier=meta.specifier,
                    caller=caller,
                )
            )
            return
        self.gaps.append(gap)

    def _gap(self, caller: str, expr: str, line: int, reason: str) -> None:
        self.gaps.append(ResolutionGap(caller, expr, line, reason, language="typescript"))

    def _resolve(
        self, func: Any, class_name: str | None
    ) -> tuple[str | None, str, str | None, str | None]:
        """Resolve a call target, or return the deferral hints for the post-pass.

        Returns ``(callee, reason, deferred_key, member)``:
          * ``callee`` — qualified in-repo symbol when resolved now, else ``None``.
          * ``reason`` — gap reason when ``callee`` is ``None``.
          * ``deferred_key`` — local binding name when this is a deferrable
            import (default export / path alias) the S4 post-pass may resolve.
          * ``member`` — accessed member name for a namespace call (``U.greet``
            -> ``"greet"``), else ``None``.

        Resolution order mirrors ``call_graph_resolve.resolve_name``: local
        module symbols first, then the lexical import-binding table. A binding we
        cannot follow yet yields its recorded deferred reason — never a guess.
        """
        if func.type == "identifier":
            name = _node_text(func, self.source)
            qname = self._local_functions.get(name)
            if qname is not None:
                return qname, "unresolved_static_call", None, None
            # Named / aliased import from an in-repo relative module (resolved).
            bound = self._named_bindings.get(name)
            if bound is not None:
                return bound, "unresolved_static_call", None, None
            # A binding we deliberately did not resolve (default / external / alias).
            deferred = self._deferred_bindings.get(name)
            if deferred is not None:
                return None, deferred, name, None
            # A bare name we do not own and never saw imported.
            return None, "import_unresolved", None, None
        if func.type == "member_expression":
            obj = func.child_by_field_name("object")
            prop = func.child_by_field_name("property")
            if obj is None or prop is None:
                return None, "unresolved_static_call", None, None
            if obj.type == "this" and class_name:
                method_name = _node_text(prop, self.source)
                qname = self._class_methods.get(f"{class_name}.{method_name}")
                if qname is not None:
                    return qname, "unresolved_static_call", None, None
                # this.<something not a known method> — dynamic within class.
                return None, "unresolved_static_call", None, None
            if obj.type == "identifier":
                obj_name = _node_text(obj, self.source)
                member = (
                    _node_text(prop, self.source) if prop.type == "property_identifier" else None
                )
                # Namespace import: `import * as U from "./util"` -> U.greet().
                ns_module = self._namespace_bindings.get(obj_name)
                if ns_module is not None and member is not None:
                    return f"{ns_module}.{member}", "unresolved_static_call", None, None
                # A namespace-like deferred binding (external `import * as fs`,
                # or a path-alias `import * as U from "@/util"` awaiting tsconfig).
                deferred = self._deferred_bindings.get(obj_name)
                if deferred is not None:
                    return None, deferred, obj_name, member
                # A local variable / typed receiver: `f.format()`. We cannot
                # know the receiver's type without a type checker — defer.
                return None, "receiver_untyped", None, None
            # obj.method() where obj is not a plain identifier (chained, etc.).
            return None, "receiver_untyped", None, None
        # call().foo(), (expr)(), tagged templates, etc.
        return None, "dynamic_dispatch", None, None

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


def _has_default_keyword(export_node: Any) -> bool:
    """True for an ``export default ...`` statement (has a ``default`` child)."""
    return any(child.type == "default" for child in export_node.children)


def _export_clause_pairs(clause: Any, source: bytes) -> list[tuple[str, str]]:
    """Yield ``(local_name, exported_name)`` for each ``export_specifier``.

    ``{ a }`` -> ``("a", "a")``; ``{ a as b }`` -> ``("a", "b")``. The local name
    is the source-module origin; the exported name is what consumers import.
    """
    out: list[tuple[str, str]] = []
    for spec in clause.children:
        if spec.type != "export_specifier":
            continue
        idents = [c for c in spec.children if c.type == "identifier"]
        if not idents:
            continue
        local = _node_text(idents[0], source)
        exported = _node_text(idents[1], source) if len(idents) >= 2 else local
        out.append((local, exported))
    return out


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
    """True for any ``export ... from "..."`` (re-export, not a local export).

    Covers both ``export { x } from "./y"`` (has ``export_clause``) and
    ``export * from "./y"`` (has a ``*`` child). The discriminator is the
    presence of a ``from`` clause: a bare ``export { x }`` (no ``from``) is a
    local export, not a re-export.
    """
    return any(child.type == "from" for child in export_node.children)


def _is_path_alias(specifier: str) -> bool:
    """True for a common tsconfig path alias (``@/util``, ``~/foo``).

    Conservative on purpose: only the ``@/`` and ``~/`` (and bare ``~``) sigils
    count. Scoped npm packages (``@angular/core``) start with ``@`` but are
    external, not aliases — misclassifying them would distort the gap taxonomy,
    so they fall through to the external ``import_unresolved`` branch.
    """
    return specifier.startswith(("@/", "~/")) or specifier == "~"
