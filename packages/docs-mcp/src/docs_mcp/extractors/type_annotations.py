"""Type annotation extraction and resolution for Python AST nodes.

Resolves Python type annotations from AST nodes and string representations
into structured, human-readable TypeInfo objects with normalization to
modern Python typing conventions.
"""

from __future__ import annotations

import ast

from pydantic import BaseModel

# Mapping of typing module generics to their lowercase builtin equivalents
_TYPING_TO_BUILTIN: dict[str, str] = {
    "List": "list",
    "Dict": "dict",
    "Tuple": "tuple",
    "Set": "set",
    "FrozenSet": "frozenset",
    "Type": "type",
}

# typing.X prefixed forms
_TYPING_DOT_TO_BUILTIN: dict[str, str] = {
    f"typing.{k}": v for k, v in _TYPING_TO_BUILTIN.items()
}


class TypeInfo(BaseModel):
    """Structured representation of a Python type annotation."""

    raw: str  # Original annotation as written
    resolved: str  # Normalized human-readable form
    is_optional: bool = False  # True if Optional[X] or X | None
    base_type: str = ""  # Primary type without Optional wrapper
    type_args: list[str] = []  # Generic type arguments
    is_generic: bool = False  # True if has type parameters
    is_callable: bool = False  # True if Callable[...]
    is_literal: bool = False  # True if Literal[...]
    is_union: bool = False  # True if X | Y or Union[X, Y]


def resolve_annotation(node: ast.expr | None) -> TypeInfo:
    """Resolve an AST annotation node into a structured TypeInfo.

    Handles all standard Python type annotation forms including generics,
    unions, Optional, Callable, Literal, ClassVar, and forward references.
    Never raises on malformed input -- returns a degraded TypeInfo instead.

    Args:
        node: An AST expression node representing a type annotation, or None.

    Returns:
        A TypeInfo with resolved type information.
    """
    if node is None:
        return TypeInfo(raw="", resolved="", base_type="")

    raw = _node_to_string(node)

    try:
        return _resolve_node(node, raw)
    except Exception:  # noqa: BLE001
        return TypeInfo(raw=raw, resolved=raw, base_type=raw)


def annotation_to_string(node: ast.expr | None) -> str:
    """Convert an AST annotation node to its string representation.

    Uses ``ast.unparse()`` as the primary mechanism, with fallbacks
    for edge cases.

    Args:
        node: An AST expression node, or None.

    Returns:
        The string representation of the annotation, or empty string if None.
    """
    if node is None:
        return ""
    return _node_to_string(node)


def parse_annotation_string(annotation_str: str) -> TypeInfo:
    """Parse a string type annotation into a TypeInfo.

    Handles annotations that come as strings (e.g., from
    ``from __future__ import annotations`` or forward references).

    Args:
        annotation_str: A string representation of a type annotation.

    Returns:
        A TypeInfo with resolved type information, or a degraded result
        if parsing fails.
    """
    if not annotation_str or not annotation_str.strip():
        return TypeInfo(raw="", resolved="", base_type="")

    annotation_str = annotation_str.strip()

    try:
        tree = ast.parse(annotation_str, mode="eval")
        return resolve_annotation(tree.body)
    except (SyntaxError, ValueError):
        return TypeInfo(
            raw=annotation_str,
            resolved=annotation_str,
            base_type=annotation_str,
        )


def _node_to_string(node: ast.expr) -> str:
    """Convert an AST node to its string representation."""
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001
        return ""


def _resolve_node(node: ast.expr, raw: str) -> TypeInfo:
    """Dispatch resolution based on AST node type."""
    if isinstance(node, ast.Constant):
        return _resolve_constant(node, raw)

    if isinstance(node, ast.Name):
        return _resolve_name(node, raw)

    if isinstance(node, ast.Attribute):
        return _resolve_attribute(node, raw)

    if isinstance(node, ast.Subscript):
        return _resolve_subscript(node, raw)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _resolve_bitor(node, raw)

    # Fallback for unrecognized node types
    return TypeInfo(raw=raw, resolved=raw, base_type=raw)


def _resolve_constant(node: ast.Constant, raw: str) -> TypeInfo:
    """Resolve a constant node (forward references or None)."""
    if isinstance(node.value, str):
        # Forward reference string -- strip quotes, parse recursively
        inner = node.value.strip()
        try:
            tree = ast.parse(inner, mode="eval")
            info = resolve_annotation(tree.body)
            # Preserve the original raw (with quotes) but use resolved from inner
            return TypeInfo(
                raw=raw,
                resolved=info.resolved,
                is_optional=info.is_optional,
                base_type=info.base_type,
                type_args=info.type_args,
                is_generic=info.is_generic,
                is_callable=info.is_callable,
                is_literal=info.is_literal,
                is_union=info.is_union,
            )
        except (SyntaxError, ValueError):
            return TypeInfo(raw=raw, resolved=inner, base_type=inner)

    if node.value is None:
        return TypeInfo(raw=raw, resolved="None", base_type="None")

    if node.value is ...:
        return TypeInfo(raw=raw, resolved="...", base_type="...")

    # Non-string constant (e.g., int literal used as annotation)
    resolved = str(node.value)
    return TypeInfo(raw=raw, resolved=resolved, base_type=resolved)


def _resolve_name(node: ast.Name, raw: str) -> TypeInfo:
    """Resolve a simple name node (str, int, Path, Any, etc.)."""
    name = node.id
    # Normalize typing capitalized generics to builtins
    if name in _TYPING_TO_BUILTIN:
        resolved = _TYPING_TO_BUILTIN[name]
        return TypeInfo(raw=raw, resolved=resolved, base_type=resolved)
    return TypeInfo(raw=raw, resolved=name, base_type=name)


def _resolve_attribute(node: ast.Attribute, raw: str) -> TypeInfo:
    """Resolve a dotted attribute node (typing.Optional, os.PathLike, etc.)."""
    full_name = _node_to_string(node)
    # Normalize typing.List → list, etc.
    if full_name in _TYPING_DOT_TO_BUILTIN:
        resolved = _TYPING_DOT_TO_BUILTIN[full_name]
        return TypeInfo(raw=raw, resolved=resolved, base_type=resolved)
    # Strip typing. prefix for simple types
    if full_name.startswith("typing."):
        short = full_name[len("typing."):]
        return TypeInfo(raw=raw, resolved=short, base_type=short)
    return TypeInfo(raw=raw, resolved=full_name, base_type=full_name)


def _resolve_subscript(node: ast.Subscript, raw: str) -> TypeInfo:
    """Resolve a subscript node (generics, Optional, Union, etc.)."""
    base_name = _node_to_string(node.value)

    # Normalize the base name
    normalized_base = _normalize_base_name(base_name)

    # Handle special forms
    if normalized_base in ("Optional",):
        return _resolve_optional(node.slice, raw)

    if normalized_base in ("Union",):
        return _resolve_union(node.slice, raw)

    if normalized_base in ("ClassVar",):
        return _resolve_classvar(node.slice, raw)

    if normalized_base in ("Callable",):
        return _resolve_callable(node.slice, raw)

    if normalized_base in ("Literal",):
        return _resolve_literal(node.slice, raw)

    # Regular generic type
    return _resolve_generic(normalized_base, node.slice, raw)


def _normalize_base_name(name: str) -> str:
    """Normalize a base type name, handling typing module prefixes."""
    # Handle typing.X prefixed names
    if name.startswith("typing."):
        short = name[len("typing."):]
        # Check if it maps to a builtin
        if short in _TYPING_TO_BUILTIN:
            return _TYPING_TO_BUILTIN[short]
        return short

    # Handle bare typing capitalized generics
    if name in _TYPING_TO_BUILTIN:
        return _TYPING_TO_BUILTIN[name]

    return name


def _resolve_optional(slice_node: ast.expr, raw: str) -> TypeInfo:
    """Resolve Optional[X] → X | None."""
    inner_info = resolve_annotation(slice_node)
    resolved = f"{inner_info.resolved} | None"
    return TypeInfo(
        raw=raw,
        resolved=resolved,
        is_optional=True,
        base_type=inner_info.resolved,
        type_args=[inner_info.resolved, "None"],
        is_generic=False,
        is_union=True,
    )


def _resolve_union(slice_node: ast.expr, raw: str) -> TypeInfo:
    """Resolve Union[X, Y, ...] → X | Y | ..."""
    args = _extract_tuple_elements(slice_node)
    resolved_args = [resolve_annotation(a).resolved for a in args]

    has_none = "None" in resolved_args
    non_none = [a for a in resolved_args if a != "None"]

    resolved = " | ".join(resolved_args)
    base = non_none[0] if len(non_none) == 1 else ""

    return TypeInfo(
        raw=raw,
        resolved=resolved,
        is_optional=has_none,
        base_type=base,
        type_args=resolved_args,
        is_generic=False,
        is_union=True,
    )


def _resolve_classvar(slice_node: ast.expr, raw: str) -> TypeInfo:
    """Resolve ClassVar[X] → show inner type."""
    inner_info = resolve_annotation(slice_node)
    return TypeInfo(
        raw=raw,
        resolved=inner_info.resolved,
        is_optional=inner_info.is_optional,
        base_type=inner_info.base_type or inner_info.resolved,
        type_args=inner_info.type_args,
        is_generic=inner_info.is_generic,
        is_callable=inner_info.is_callable,
        is_literal=inner_info.is_literal,
        is_union=inner_info.is_union,
    )


def _resolve_callable(slice_node: ast.expr, raw: str) -> TypeInfo:
    """Resolve Callable[[args], return_type]."""
    args = _extract_tuple_elements(slice_node)
    resolved_args: list[str] = []
    for a in args:
        resolved_args.append(resolve_annotation(a).resolved)

    # Reconstruct normalized form
    if len(resolved_args) >= 2:  # noqa: PLR2004
        param_part = resolved_args[0]
        return_part = resolved_args[1]
        resolved = f"Callable[{param_part}, {return_part}]"
    else:
        resolved = f"Callable[{', '.join(resolved_args)}]"

    return TypeInfo(
        raw=raw,
        resolved=resolved,
        is_callable=True,
        base_type="Callable",
        type_args=resolved_args,
        is_generic=True,
    )


def _resolve_literal(slice_node: ast.expr, raw: str) -> TypeInfo:
    """Resolve Literal["a", "b", 1]."""
    args = _extract_tuple_elements(slice_node)
    resolved_args: list[str] = []
    for a in args:
        resolved_args.append(_node_to_string(a))

    inner = ", ".join(resolved_args)
    resolved = f"Literal[{inner}]"

    return TypeInfo(
        raw=raw,
        resolved=resolved,
        is_literal=True,
        base_type="Literal",
        type_args=resolved_args,
        is_generic=True,
    )


def _resolve_generic(base: str, slice_node: ast.expr, raw: str) -> TypeInfo:
    """Resolve a generic type like list[str], dict[str, int], etc."""
    args = _extract_tuple_elements(slice_node)
    resolved_args: list[str] = []
    for a in args:
        info = resolve_annotation(a)
        resolved_args.append(info.resolved)

    inner = ", ".join(resolved_args)
    resolved = f"{base}[{inner}]"

    return TypeInfo(
        raw=raw,
        resolved=resolved,
        is_generic=True,
        base_type=base,
        type_args=resolved_args,
    )


def _resolve_bitor(node: ast.BinOp, raw: str) -> TypeInfo:
    """Resolve X | Y union syntax (Python 3.10+)."""
    parts = _flatten_bitor(node)
    resolved_args = [resolve_annotation(p).resolved for p in parts]

    has_none = "None" in resolved_args
    non_none = [a for a in resolved_args if a != "None"]

    resolved = " | ".join(resolved_args)
    base = non_none[0] if has_none and len(non_none) == 1 else ""

    return TypeInfo(
        raw=raw,
        resolved=resolved,
        is_optional=has_none,
        base_type=base,
        type_args=resolved_args,
        is_union=True,
    )


def _flatten_bitor(node: ast.expr) -> list[ast.expr]:
    """Flatten nested BinOp(|) into a flat list of operands."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _flatten_bitor(node.left) + _flatten_bitor(node.right)
    return [node]


def _extract_tuple_elements(node: ast.expr) -> list[ast.expr]:
    """Extract elements from a Tuple node, or wrap a single node in a list."""
    if isinstance(node, ast.Tuple):
        return list(node.elts)
    return [node]
