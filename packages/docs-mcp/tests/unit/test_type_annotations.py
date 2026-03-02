"""Tests for the type annotation extractor.

Covers simple types, optional, union, generic containers, Callable,
Literal, normalization, string parsing, and edge cases.
"""

from __future__ import annotations

import ast

import pytest

from docs_mcp.extractors.type_annotations import (
    TypeInfo,
    annotation_to_string,
    parse_annotation_string,
    resolve_annotation,
)


def _parse_expr(code: str) -> ast.expr:
    """Parse a Python expression string into an AST expression node."""
    tree = ast.parse(code, mode="eval")
    return tree.body


# ---------------------------------------------------------------------------
# Simple types
# ---------------------------------------------------------------------------


class TestSimpleTypes:
    """Tests for basic type annotations."""

    def test_str(self) -> None:
        node = _parse_expr("str")
        info = resolve_annotation(node)
        assert info.resolved == "str"
        assert info.base_type == "str"
        assert info.is_optional is False
        assert info.is_generic is False

    def test_int(self) -> None:
        node = _parse_expr("int")
        info = resolve_annotation(node)
        assert info.resolved == "int"
        assert info.base_type == "int"

    def test_float(self) -> None:
        node = _parse_expr("float")
        info = resolve_annotation(node)
        assert info.resolved == "float"

    def test_bool(self) -> None:
        node = _parse_expr("bool")
        info = resolve_annotation(node)
        assert info.resolved == "bool"

    def test_none_type(self) -> None:
        node = _parse_expr("None")
        info = resolve_annotation(node)
        assert info.resolved == "None"

    def test_path(self) -> None:
        node = _parse_expr("Path")
        info = resolve_annotation(node)
        assert info.resolved == "Path"
        assert info.base_type == "Path"

    def test_any(self) -> None:
        node = _parse_expr("Any")
        info = resolve_annotation(node)
        assert info.resolved == "Any"

    def test_none_input(self) -> None:
        info = resolve_annotation(None)
        assert info.raw == ""
        assert info.resolved == ""
        assert info.base_type == ""


# ---------------------------------------------------------------------------
# Optional types
# ---------------------------------------------------------------------------


class TestOptionalTypes:
    """Tests for Optional[X] and X | None annotations."""

    def test_optional_subscript(self) -> None:
        node = _parse_expr("Optional[str]")
        info = resolve_annotation(node)
        assert info.is_optional is True
        assert info.base_type == "str"
        assert info.resolved == "str | None"
        assert info.is_union is True

    def test_pipe_none(self) -> None:
        node = _parse_expr("str | None")
        info = resolve_annotation(node)
        assert info.is_optional is True
        assert info.base_type == "str"
        assert info.resolved == "str | None"
        assert info.is_union is True

    def test_union_with_none(self) -> None:
        node = _parse_expr("Union[str, None]")
        info = resolve_annotation(node)
        assert info.is_optional is True
        assert info.base_type == "str"
        assert info.resolved == "str | None"
        assert info.is_union is True


# ---------------------------------------------------------------------------
# Union types
# ---------------------------------------------------------------------------


class TestUnionTypes:
    """Tests for Union[X, Y] and X | Y annotations."""

    def test_pipe_union(self) -> None:
        node = _parse_expr("str | int")
        info = resolve_annotation(node)
        assert info.is_union is True
        assert info.is_optional is False
        assert info.resolved == "str | int"
        assert info.type_args == ["str", "int"]

    def test_union_subscript(self) -> None:
        node = _parse_expr("Union[str, int, float]")
        info = resolve_annotation(node)
        assert info.is_union is True
        assert info.is_optional is False
        assert info.resolved == "str | int | float"
        assert info.type_args == ["str", "int", "float"]

    def test_pipe_union_with_none(self) -> None:
        node = _parse_expr("str | int | None")
        info = resolve_annotation(node)
        assert info.is_union is True
        assert info.is_optional is True
        assert info.resolved == "str | int | None"
        assert info.type_args == ["str", "int", "None"]


# ---------------------------------------------------------------------------
# Generic containers
# ---------------------------------------------------------------------------


class TestGenericContainers:
    """Tests for generic container types."""

    def test_list_str(self) -> None:
        node = _parse_expr("list[str]")
        info = resolve_annotation(node)
        assert info.is_generic is True
        assert info.base_type == "list"
        assert info.type_args == ["str"]
        assert info.resolved == "list[str]"

    def test_dict_str_int(self) -> None:
        node = _parse_expr("dict[str, int]")
        info = resolve_annotation(node)
        assert info.is_generic is True
        assert info.base_type == "dict"
        assert info.type_args == ["str", "int"]
        assert info.resolved == "dict[str, int]"

    def test_tuple_multi(self) -> None:
        node = _parse_expr("tuple[int, str, float]")
        info = resolve_annotation(node)
        assert info.is_generic is True
        assert info.type_args == ["int", "str", "float"]
        assert info.resolved == "tuple[int, str, float]"

    def test_tuple_ellipsis(self) -> None:
        node = _parse_expr("tuple[int, ...]")
        info = resolve_annotation(node)
        assert info.is_generic is True
        assert info.resolved == "tuple[int, ...]"

    def test_set_str(self) -> None:
        node = _parse_expr("set[str]")
        info = resolve_annotation(node)
        assert info.is_generic is True
        assert info.base_type == "set"
        assert info.type_args == ["str"]

    def test_nested_generic(self) -> None:
        node = _parse_expr("list[dict[str, list[int]]]")
        info = resolve_annotation(node)
        assert info.is_generic is True
        assert info.base_type == "list"
        assert info.resolved == "list[dict[str, list[int]]]"
        assert info.type_args == ["dict[str, list[int]]"]

    def test_frozenset(self) -> None:
        node = _parse_expr("frozenset[int]")
        info = resolve_annotation(node)
        assert info.is_generic is True
        assert info.base_type == "frozenset"
        assert info.type_args == ["int"]


# ---------------------------------------------------------------------------
# Callable types
# ---------------------------------------------------------------------------


class TestCallableTypes:
    """Tests for Callable annotations."""

    def test_callable_params_return(self) -> None:
        node = _parse_expr("Callable[[int, str], bool]")
        info = resolve_annotation(node)
        assert info.is_callable is True
        assert info.base_type == "Callable"
        assert info.is_generic is True
        assert "Callable[" in info.resolved
        assert "bool" in info.resolved

    def test_callable_ellipsis(self) -> None:
        node = _parse_expr("Callable[..., None]")
        info = resolve_annotation(node)
        assert info.is_callable is True
        assert info.base_type == "Callable"
        assert "None" in info.resolved


# ---------------------------------------------------------------------------
# Literal types
# ---------------------------------------------------------------------------


class TestLiteralTypes:
    """Tests for Literal annotations."""

    def test_literal_strings(self) -> None:
        node = _parse_expr("Literal['a', 'b']")
        info = resolve_annotation(node)
        assert info.is_literal is True
        assert info.base_type == "Literal"
        assert info.is_generic is True
        assert "Literal[" in info.resolved

    def test_literal_ints(self) -> None:
        node = _parse_expr("Literal[1, 2, 3]")
        info = resolve_annotation(node)
        assert info.is_literal is True
        assert info.base_type == "Literal"
        assert "Literal[" in info.resolved


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


class TestNormalization:
    """Tests for type annotation normalization to modern Python style."""

    def test_typing_optional(self) -> None:
        node = _parse_expr("typing.Optional[str]")
        info = resolve_annotation(node)
        assert info.resolved == "str | None"
        assert info.is_optional is True

    def test_typing_list(self) -> None:
        node = _parse_expr("typing.List[str]")
        info = resolve_annotation(node)
        assert info.resolved == "list[str]"
        assert info.base_type == "list"

    def test_typing_dict(self) -> None:
        node = _parse_expr("typing.Dict[str, int]")
        info = resolve_annotation(node)
        assert info.resolved == "dict[str, int]"
        assert info.base_type == "dict"

    def test_typing_tuple(self) -> None:
        node = _parse_expr("typing.Tuple[int, str]")
        info = resolve_annotation(node)
        assert info.resolved == "tuple[int, str]"

    def test_typing_set(self) -> None:
        node = _parse_expr("typing.Set[int]")
        info = resolve_annotation(node)
        assert info.resolved == "set[int]"

    def test_typing_frozenset(self) -> None:
        node = _parse_expr("typing.FrozenSet[int]")
        info = resolve_annotation(node)
        assert info.resolved == "frozenset[int]"

    def test_forward_reference(self) -> None:
        node = _parse_expr("'MyClass'")
        info = resolve_annotation(node)
        assert info.resolved == "MyClass"
        assert info.base_type == "MyClass"

    def test_bare_capitalized_list(self) -> None:
        """Bare `List` (imported from typing) normalizes to `list`."""
        node = _parse_expr("List")
        info = resolve_annotation(node)
        assert info.resolved == "list"

    def test_bare_capitalized_dict(self) -> None:
        node = _parse_expr("Dict")
        info = resolve_annotation(node)
        assert info.resolved == "dict"

    def test_typing_attribute_simple(self) -> None:
        """typing.Any should normalize to just Any."""
        node = _parse_expr("typing.Any")
        info = resolve_annotation(node)
        assert info.resolved == "Any"

    def test_sequence_kept(self) -> None:
        """Sequence[X] is an abstract type and should be kept as-is."""
        node = _parse_expr("Sequence[int]")
        info = resolve_annotation(node)
        assert info.resolved == "Sequence[int]"


# ---------------------------------------------------------------------------
# String parsing
# ---------------------------------------------------------------------------


class TestStringParsing:
    """Tests for parse_annotation_string()."""

    def test_str_or_none(self) -> None:
        info = parse_annotation_string("str | None")
        assert info.is_optional is True
        assert info.resolved == "str | None"
        assert info.base_type == "str"

    def test_nested_generic(self) -> None:
        info = parse_annotation_string("list[dict[str, int]]")
        assert info.is_generic is True
        assert info.resolved == "list[dict[str, int]]"

    def test_invalid_string(self) -> None:
        info = parse_annotation_string("not a valid[type")
        assert info.raw == "not a valid[type"
        assert info.resolved == "not a valid[type"

    def test_empty_string(self) -> None:
        info = parse_annotation_string("")
        assert info.raw == ""
        assert info.resolved == ""

    def test_whitespace_only(self) -> None:
        info = parse_annotation_string("   ")
        assert info.raw == ""
        assert info.resolved == ""

    def test_simple_name(self) -> None:
        info = parse_annotation_string("int")
        assert info.resolved == "int"
        assert info.base_type == "int"


# ---------------------------------------------------------------------------
# annotation_to_string
# ---------------------------------------------------------------------------


class TestAnnotationToString:
    """Tests for annotation_to_string()."""

    def test_none_returns_empty(self) -> None:
        assert annotation_to_string(None) == ""

    def test_simple_name(self) -> None:
        node = _parse_expr("str")
        assert annotation_to_string(node) == "str"

    def test_generic(self) -> None:
        node = _parse_expr("list[int]")
        result = annotation_to_string(node)
        assert result == "list[int]"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_classvar_int(self) -> None:
        node = _parse_expr("ClassVar[int]")
        info = resolve_annotation(node)
        assert info.resolved == "int"
        assert info.base_type == "int"

    def test_type_subscript(self) -> None:
        node = _parse_expr("type[MyClass]")
        info = resolve_annotation(node)
        assert info.is_generic is True
        assert info.resolved == "type[MyClass]"
        assert info.base_type == "type"

    def test_constant_non_string(self) -> None:
        """An integer constant used as annotation returns degraded result."""
        # Create a Constant node with a non-string value directly
        node = ast.Constant(value=42)
        info = resolve_annotation(node)
        assert info.resolved == "42"

    def test_dotted_attribute(self) -> None:
        node = _parse_expr("os.PathLike")
        info = resolve_annotation(node)
        assert info.resolved == "os.PathLike"
        assert info.base_type == "os.PathLike"

    def test_forward_ref_complex(self) -> None:
        """Forward reference containing a generic resolves correctly."""
        node = _parse_expr("'list[int]'")
        info = resolve_annotation(node)
        assert info.resolved == "list[int]"
        assert info.is_generic is True

    def test_optional_generic(self) -> None:
        """Optional[list[str]] resolves correctly."""
        node = _parse_expr("Optional[list[str]]")
        info = resolve_annotation(node)
        assert info.is_optional is True
        assert info.base_type == "list[str]"
        assert info.resolved == "list[str] | None"

    def test_union_two_generics(self) -> None:
        node = _parse_expr("Union[list[str], dict[str, int]]")
        info = resolve_annotation(node)
        assert info.is_union is True
        assert "list[str]" in info.resolved
        assert "dict[str, int]" in info.resolved

    def test_deeply_nested(self) -> None:
        node = _parse_expr("dict[str, list[tuple[int, ...]]]")
        info = resolve_annotation(node)
        assert info.is_generic is True
        assert info.base_type == "dict"
        assert info.resolved == "dict[str, list[tuple[int, ...]]]"

    def test_typing_type_subscript(self) -> None:
        """typing.Type[X] normalizes to type[X]."""
        node = _parse_expr("typing.Type[int]")
        info = resolve_annotation(node)
        assert info.resolved == "type[int]"
        assert info.base_type == "type"
