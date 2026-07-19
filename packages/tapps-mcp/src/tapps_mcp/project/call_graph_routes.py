"""HTTP route -> handler edge extraction (TAP-4532).

Models the endpoint <-> handler relationship as a first-class ``RouteEdge`` so an
agent can ask "which handler serves path X" and "which routes break if I change
handler Y" (blast radius). Two frameworks are covered:

* **FastAPI (Python ``ast``)** — decorator routes ``@app.get("/x")``,
  ``@router.post("/y")``, ``@some_router.route("/z")`` on ``APIRouter``/``FastAPI``
  instances. The decorated function is the handler symbol (qualified with the same
  scheme as ``call_graph_analyze``); the HTTP verb is the decorator method and the
  first string-literal argument is the path.

* **React Router (TypeScript, tree-sitter)** — two forms:

  * the JSX ``<Route path="/x" element={<Comp/>} />`` element form; and
  * the object-literal ``createBrowserRouter([{path, element}])`` /
    ``createHashRouter([...])`` form (TAP-4551), including nested ``children``
    arrays with static parent+child path composition.

  In both, the component named in ``element`` is the handler symbol; when the
  component is imported from an in-repo relative module the symbol is qualified
  to ``<module>.<Comp>``, otherwise the bare local name is kept.

Deterministic contract (ADR-0004): no LLM, no network. A route whose path or
handler cannot be read from a literal (dynamic ``add_api_route`` calls, a spread
``{...route}`` element, ``element={route.el}``, a computed / non-literal path
expression) is simply **not emitted** — never a guessed edge. For the
object-literal form, path composition (parent + child) is applied only when both
segments are string literals; a non-literal segment leaves the child with its own
literal path (or omits it entirely), never a fabricated join.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from tapps_mcp.project.call_graph_analyze_ts import (
    _TSX_LANGUAGE,
    HAS_TREE_SITTER,
    _import_specifier,
    _iter_statements,
    _named_import_pairs,
    _node_text,
    _resolve_relative_module,
)
from tapps_mcp.project.call_graph_types import RouteEdge

# Guard tree-sitter import for graceful degradation (mirrors call_graph_analyze_ts).
try:
    import tree_sitter
except ImportError:  # pragma: no cover - exercised only when grammar absent
    tree_sitter = None  # type: ignore[assignment]

# HTTP verbs FastAPI exposes as decorator methods on ``FastAPI`` / ``APIRouter``.
_FASTAPI_HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)
# ``@app.route("/x")`` (Starlette/Flask-style) carries no single verb; record it
# under the generic ROUTE method so it is still queryable.
_FASTAPI_GENERIC = "route"


def extract_fastapi_routes(
    file_path: Path,
    module: str,
    project_root: Path,
) -> list[RouteEdge]:
    """Extract FastAPI decorator route -> handler edges from a Python file.

    Returns one ``RouteEdge`` per ``@<router>.<verb>("path")`` decorator on a
    module-level or method function. A decorator whose first argument is not a
    string literal (dynamic path) is skipped, not guessed.
    """
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    try:
        rel_path = str(file_path.relative_to(project_root))
    except ValueError:
        rel_path = str(file_path)

    routes: list[RouteEdge] = []
    _scan_body(tree.body, module=module, outer=[], rel_path=rel_path, routes=routes)
    return routes


def _scan_body(
    body: list[ast.stmt],
    *,
    module: str,
    outer: list[str],
    rel_path: str,
    routes: list[RouteEdge],
) -> None:
    for node in body:
        if isinstance(node, ast.ClassDef):
            _scan_body(
                node.body,
                module=module,
                outer=[*outer, node.name],
                rel_path=rel_path,
                routes=routes,
            )
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            handler = ".".join([module, *outer, node.name])
            for dec in node.decorator_list:
                edge = _route_edge_from_decorator(dec, handler, rel_path)
                if edge is not None:
                    routes.append(edge)


def _route_edge_from_decorator(
    dec: ast.expr,
    handler: str,
    rel_path: str,
) -> RouteEdge | None:
    """Turn a ``@router.get("/x")`` decorator into a RouteEdge, or ``None``.

    Only ``Call`` decorators of the shape ``<attr>.<verb>(<str>, ...)`` where
    ``<verb>`` is a known FastAPI HTTP method (or the generic ``route``) produce
    an edge. The path must be a string literal — a non-literal first argument is
    a dynamic route we refuse to guess.
    """
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not isinstance(func, ast.Attribute):
        return None
    verb = func.attr.lower()
    if verb not in _FASTAPI_HTTP_METHODS and verb != _FASTAPI_GENERIC:
        return None
    path = _first_string_arg(dec)
    if path is None:
        return None
    method = "ROUTE" if verb == _FASTAPI_GENERIC else verb.upper()
    return RouteEdge(
        method=method,
        path=path,
        handler_symbol=handler,
        framework="fastapi",
        file_path=rel_path,
        line=dec.lineno,
    )


def _first_string_arg(call: ast.Call) -> str | None:
    """The first positional string-literal argument of *call*, or ``None``."""
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        # First positional arg is not a string literal -> dynamic path.
        return None
    return None


# ----------------------------------------------------------------------
# React Router (TypeScript / JSX)
# ----------------------------------------------------------------------


def extract_react_router_routes(
    file_path: Path,
    module: str,
    project_root: Path,
) -> list[RouteEdge]:
    """Extract React Router route -> component edges (JSX + object-literal forms).

    Covers both the JSX ``<Route path=... element={<Comp/>} />`` element form and
    the ``createBrowserRouter([...])`` / ``createHashRouter([...])`` object-literal
    form (TAP-4551), the latter including nested ``children`` arrays with static
    parent+child path composition. A route missing a literal ``path`` or a
    nameable ``element`` component is skipped, never guessed.

    The component's handler symbol is qualified to ``<target_module>.<Comp>`` when
    the component is imported from an in-repo relative module; otherwise the bare
    component name is used (never a fabricated cross-module target).
    """
    if not HAS_TREE_SITTER or _TSX_LANGUAGE is None:
        return []
    if file_path.suffix.lower() != ".tsx":
        # React Router JSX only appears in ``.tsx`` files.
        return []
    try:
        source = file_path.read_bytes()
        source.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        rel_path = str(file_path.relative_to(project_root))
    except ValueError:
        rel_path = str(file_path)

    try:
        parser = tree_sitter.Parser(_TSX_LANGUAGE)
        tree = parser.parse(source)
    except Exception:  # pragma: no cover - defensive
        return []
    root = tree.root_node
    if root.has_error:
        return []

    component_modules = _react_component_import_modules(root, source, module)
    routes: list[RouteEdge] = []
    _walk_jsx_routes(root, source, rel_path, component_modules, routes)
    _walk_object_router_calls(root, source, rel_path, component_modules, routes)
    return routes


def _react_component_import_modules(root: Any, source: bytes, module: str) -> dict[str, str]:
    """Map an imported component's local name -> resolved in-repo module.

    Handles both ``import Comp from "./Comp"`` (default) and
    ``import { Comp } from "./Comp"`` (named), but only for relative specifiers
    that resolve inside the repo. Non-relative / path-alias imports are omitted so
    the caller falls back to the bare component name.
    """
    out: dict[str, str] = {}
    for node in _iter_statements(root):
        if node.type != "import_statement":
            continue
        specifier = _import_specifier(node, source)
        if specifier is None or not specifier.startswith("."):
            continue
        target = _resolve_relative_module(module, specifier)
        if target is None:
            continue
        clause = None
        for child in node.children:
            if child.type == "import_clause":
                clause = child
                break
        if clause is None:
            continue
        for child in clause.children:
            if child.type == "identifier":
                # Default import: `import Comp from "./Comp"`.
                out[_node_text(child, source)] = target
            elif child.type == "named_imports":
                for local, _real in _named_import_pairs(child, source):
                    out[local] = target
    return out


def _walk_jsx_routes(
    node: Any,
    source: bytes,
    rel_path: str,
    component_modules: dict[str, str],
    routes: list[RouteEdge],
) -> None:
    """Depth-first walk collecting ``<Route>`` JSX elements."""
    if node.type in {"jsx_self_closing_element", "jsx_opening_element"}:
        name = _jsx_element_name(node, source)
        if name == "Route":
            edge = _route_edge_from_jsx(node, source, rel_path, component_modules)
            if edge is not None:
                routes.append(edge)
    for child in node.children:
        _walk_jsx_routes(child, source, rel_path, component_modules, routes)


def _jsx_element_name(element: Any, source: bytes) -> str | None:
    """The tag name of a jsx opening/self-closing element (first ``identifier``)."""
    for child in element.children:
        if child.type == "identifier":
            return _node_text(child, source)
    return None


def _route_edge_from_jsx(
    element: Any,
    source: bytes,
    rel_path: str,
    component_modules: dict[str, str],
) -> RouteEdge | None:
    path: str | None = None
    component: str | None = None
    for child in element.children:
        if child.type != "jsx_attribute":
            continue
        attr_name = _jsx_attr_name(child, source)
        if attr_name == "path":
            path = _jsx_attr_string(child, source)
        elif attr_name == "element":
            component = _jsx_element_component(child, source)
    if path is None or component is None:
        return None
    line = int(element.start_point[0]) + 1
    return _build_react_route_edge(path, component, rel_path, component_modules, line)


def _build_react_route_edge(
    path: str,
    component: str,
    rel_path: str,
    component_modules: dict[str, str],
    line: int,
) -> RouteEdge:
    """Build a react-router RouteEdge, resolving the component via the import table.

    Shared by the JSX ``<Route>`` and object-literal ``createBrowserRouter`` paths
    so component resolution (bare name vs ``<module>.<Comp>``) stays in one place.
    """
    handler = component
    target = component_modules.get(component)
    if target is not None:
        handler = f"{target}.{component}"
    return RouteEdge(
        method="ROUTE",
        path=path,
        handler_symbol=handler,
        framework="react-router",
        file_path=rel_path,
        line=line,
    )


def _jsx_attr_name(attr: Any, source: bytes) -> str | None:
    for child in attr.children:
        if child.type == "property_identifier":
            return _node_text(child, source)
    return None


def _jsx_attr_string(attr: Any, source: bytes) -> str | None:
    """The string-literal value of a JSX attribute (``path="/x"``), or ``None``."""
    for child in attr.children:
        if child.type == "string":
            for frag in child.children:
                if frag.type == "string_fragment":
                    return _node_text(frag, source)
            # Empty string literal (``path=""``).
            return ""
    return None


def _jsx_element_component(attr: Any, source: bytes) -> str | None:
    """Component name inside ``element={<Comp/>}``, or ``None`` if not nameable.

    A spread or expression that is not a plain JSX element (``element={route.el}``)
    yields no component -> the route is skipped rather than guessed.
    """
    for child in attr.children:
        if child.type != "jsx_expression":
            continue
        for inner in child.children:
            name = _component_name_from_jsx_node(inner, source)
            if name is not None:
                return name
    return None


def _component_name_from_jsx_node(node: Any, source: bytes) -> str | None:
    """Component name of a bare JSX element node, or ``None`` if not a JSX element.

    Accepts a ``jsx_self_closing_element`` (``<Comp/>``) or ``jsx_element``
    (``<Comp>...</Comp>``) node directly. A non-JSX value (``member_expression``,
    spread, etc.) yields ``None`` -> the route is skipped, never guessed.
    """
    if node.type not in {"jsx_self_closing_element", "jsx_element"}:
        return None
    target = node
    if node.type == "jsx_element":
        # <Comp>...</Comp> -> use the opening element's name.
        for sub in node.children:
            if sub.type == "jsx_opening_element":
                target = sub
                break
    return _jsx_element_name(target, source)


# ----------------------------------------------------------------------
# React Router object-literal form: createBrowserRouter / createHashRouter (TAP-4551)
# ----------------------------------------------------------------------

_OBJECT_ROUTER_FACTORIES = frozenset({"createBrowserRouter", "createHashRouter"})


def _walk_object_router_calls(
    node: Any,
    source: bytes,
    rel_path: str,
    component_modules: dict[str, str],
    routes: list[RouteEdge],
) -> None:
    """Depth-first walk collecting ``createBrowserRouter``/``createHashRouter`` calls."""
    if node.type == "call_expression":
        callee = node.child_by_field_name("function")
        if (
            callee is not None
            and callee.type == "identifier"
            and _node_text(callee, source) in _OBJECT_ROUTER_FACTORIES
        ):
            route_array = _first_array_argument(node)
            if route_array is not None:
                _collect_route_objects(
                    route_array, source, rel_path, component_modules, routes, parent_path=None
                )
    for child in node.children:
        _walk_object_router_calls(child, source, rel_path, component_modules, routes)


def _first_array_argument(call: Any) -> Any | None:
    """The ``array`` node of the call's first argument, or ``None``."""
    args = call.child_by_field_name("arguments")
    if args is None:
        return None
    for child in args.children:
        if child.type == "array":
            return child
        if child.type in {"(", ")", ","}:
            continue
        # First real argument is not an array literal -> nothing to extract.
        return None
    return None


def _collect_route_objects(
    array_node: Any,
    source: bytes,
    rel_path: str,
    component_modules: dict[str, str],
    routes: list[RouteEdge],
    *,
    parent_path: str | None,
) -> None:
    """Emit edges for each ``{path, element, children}`` object in *array_node*.

    ``parent_path`` is the statically-composed path of the enclosing route, or
    ``None`` when the parent path was non-literal / absent. Composition is applied
    only when both parent and child paths are string literals.
    """
    for element in array_node.children:
        if element.type != "object":
            continue
        raw_path = _object_pair_string(element, "path", source)
        composed = _compose_route_path(parent_path, raw_path)

        element_value = _object_pair_value(element, "element", source)
        if element_value is not None and raw_path is not None:
            component = _component_name_from_jsx_node(element_value, source)
            if component is not None:
                line = int(element.start_point[0]) + 1
                routes.append(
                    _build_react_route_edge(
                        composed if composed is not None else raw_path,
                        component,
                        rel_path,
                        component_modules,
                        line,
                    )
                )

        children = _object_pair_value(element, "children", source)
        if children is not None and children.type == "array":
            _collect_route_objects(
                children,
                source,
                rel_path,
                component_modules,
                routes,
                parent_path=composed,
            )


def _object_pair_value(obj: Any, key: str, source: bytes) -> Any | None:
    """The value node of ``{key: <value>}`` inside an object literal, or ``None``."""
    for child in obj.children:
        if child.type != "pair":
            continue
        pair_key = child.child_by_field_name("key")
        if pair_key is None or _node_text(pair_key, source) != key:
            continue
        return child.child_by_field_name("value")
    return None


def _object_pair_string(obj: Any, key: str, source: bytes) -> str | None:
    """Literal string value of ``{key: "..."}``, or ``None`` if absent/non-literal."""
    value = _object_pair_value(obj, key, source)
    if value is None or value.type != "string":
        return None
    for frag in value.children:
        if frag.type == "string_fragment":
            return _node_text(frag, source)
    # Empty string literal (``path: ""``).
    return ""


def _compose_route_path(parent_path: str | None, child_path: str | None) -> str | None:
    """Join *parent_path* + *child_path*, normalizing slashes, or ``None``.

    Composition is only statically determinable when both segments are literal
    strings. If the child path is absent or non-literal, or the parent was
    non-literal (``None``), the child path stands on its own — never a guessed join.
    """
    if child_path is None:
        return None
    if parent_path is None:
        return child_path
    if child_path.startswith("/"):
        # Absolute child path ignores the parent (React Router semantics).
        return child_path
    left = parent_path.rstrip("/")
    right = child_path.lstrip("/")
    if not right:
        return left or "/"
    if not left:
        return f"/{right}" if parent_path.startswith("/") else right
    return f"{left}/{right}"


# ----------------------------------------------------------------------
# Query helpers (TAP-4532 AC2)
# ----------------------------------------------------------------------


def handlers_for_path(routes: list[RouteEdge], path: str) -> list[RouteEdge]:
    """Route edges whose path matches *path* exactly (deterministic, no globbing)."""
    return [r for r in routes if r.path == path]


def routes_for_handler(routes: list[RouteEdge], handler: str) -> list[RouteEdge]:
    """Route edges whose handler is *handler* (exact or short-name suffix match).

    Blast radius: which routes break if this handler symbol changes. A short name
    (``list_users``) matches any qualified handler ending in ``.list_users``; an
    exact qualified name matches only itself.
    """
    trimmed = handler.strip()
    if not trimmed:
        return []
    exact = [r for r in routes if r.handler_symbol == trimmed]
    if exact:
        return exact
    return [
        r for r in routes if r.handler_symbol == trimmed or r.handler_symbol.endswith(f".{trimmed}")
    ]
