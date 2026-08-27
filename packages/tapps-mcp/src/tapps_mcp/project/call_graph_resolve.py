"""Static call resolution helpers for call graph indexing (TAP-4053)."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.project.call_graph_analyze import FileIndex

# TAP-6439. Marker for a local whose type is written down in the source as a
# builtin display (``lines = []``, ``bindings = {}``, ``seen = set()``). Calls on
# such a receiver are ``list.append`` / ``dict.get`` / ``set.add`` — never an
# in-repo edge, even when the repo happens to define a method of that name. The
# marker is not a dotted path, so ``resolve_attribute`` can never turn it into a
# callee; it exists only to let the analyzer record an accurate gap cause.
BUILTIN_RECEIVER = "!builtin"

_BUILTIN_DISPLAY_CONSTRUCTORS = frozenset(
    {"list", "dict", "set", "tuple", "str", "bytes", "frozenset"}
)


def _is_builtin_display(value: ast.expr) -> bool:
    """True when *value*'s type is literally written in the source.

    Only forms whose runtime type is unambiguous from the syntax alone: display
    literals, comprehensions, f-strings, and no-argument builtin container
    constructors. Deliberately excludes anything requiring inference (a call
    returning a list, an annotation, a subscript) — the point is a proof, not a
    guess.
    """
    if isinstance(value, ast.List | ast.Dict | ast.Set | ast.Tuple | ast.JoinedStr):
        return True
    if isinstance(value, ast.ListComp | ast.DictComp | ast.SetComp):
        return True
    if isinstance(value, ast.Constant):
        return isinstance(value.value, str | bytes)
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in _BUILTIN_DISPLAY_CONSTRUCTORS
    )


def _is_builtin_annotation(ann: ast.expr | None) -> bool:
    """True when an annotation names a builtin container/str type.

    ``x: dict[str, str]``, ``x: list[int]``, ``x: str``. Only consulted after
    ``_annotation_target`` has failed to find a local class or imported name, so
    an in-repo class can never be shadowed by this check. The subscript is
    stripped because only the head decides the runtime type.
    """
    if isinstance(ann, ast.Subscript):
        ann = ann.value
    return isinstance(ann, ast.Name) and ann.id in _BUILTIN_DISPLAY_CONSTRUCTORS


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
        name = (
            candidate if candidate and all(p.isidentifier() for p in candidate.split(".")) else None
        )
    if not name:
        return None
    head, _, rest = name.partition(".")
    if head in idx.classes:
        base = idx.classes[head]
    elif head in idx.imports:
        base = idx.imports[head]
    else:
        return None
    return f"{base}.{rest}" if rest else base


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

    def _walk_outer_scope(root: ast.AST) -> list[ast.AST]:
        """Descendants of *root*, skipping nested function/class bodies."""
        out: list[ast.AST] = []
        for child in ast.iter_child_nodes(root):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            out.append(child)
            out.extend(_walk_outer_scope(child))
        return out

    for child in _walk_outer_scope(node):
        if isinstance(child, ast.Import | ast.ImportFrom):
            _apply_import_bindings(bindings, child)
            continue
        if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
            # Annotated local: ``w: Worker`` / ``w: Worker = factory()``.
            annotated = _annotation_target(idx, child.annotation)
            if annotated:
                bindings[child.target.id] = annotated
            elif _is_builtin_annotation(child.annotation):
                bindings[child.target.id] = BUILTIN_RECEIVER
            continue
        if not isinstance(child, ast.Assign):
            continue
        for target in child.targets:
            if not isinstance(target, ast.Name):
                continue
            if _is_builtin_display(child.value):
                bindings[target.id] = BUILTIN_RECEIVER
            elif isinstance(child.value, ast.Name):
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
    if bound == BUILTIN_RECEIVER:
        return None
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
        if bound == BUILTIN_RECEIVER:
            return None
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


def is_external_receiver(node: ast.Attribute, bindings: dict[str, str]) -> bool:
    """True when *node*'s receiver is provably a builtin, so the call leaves the repo.

    Two proofs, both syntactic (TAP-6439):

    * a literal receiver — ``"\\n".join(...)``, ``{"a", "b"}.issubset(...)``,
      ``f"{x}".strip()``;
    * a local bound to a builtin display earlier in the same function —
      ``lines = []`` then ``lines.append(...)``.

    Without this the gap is recorded as ``unresolved_static_call`` and counted
    as in-repo debt whenever the repo happens to define a method of the same
    name (``get``, ``add``, ``append``, ``search``), which is most of them.
    """
    receiver = node.value
    if _is_builtin_display(receiver):
        return True
    return isinstance(receiver, ast.Name) and bindings.get(receiver.id) == BUILTIN_RECEIVER
