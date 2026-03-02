"""Tests for the docstring parser module."""

from __future__ import annotations

from docs_mcp.extractors.docstring_parser import (
    ParsedDocstring,
    parse_docstring,
)

# ===================================================================
# Google style tests
# ===================================================================


class TestGoogleStyle:
    """Tests for Google-style docstring parsing."""

    def test_simple_summary_only(self) -> None:
        result = parse_docstring("Do something useful.")
        assert result.summary == "Do something useful."
        assert result.description == ""
        assert result.params == []
        assert result.raw == "Do something useful."

    def test_summary_and_description(self) -> None:
        doc = """\
Short summary.

This is a longer description that explains
what the function does in more detail."""
        result = parse_docstring(doc)
        assert result.summary == "Short summary."
        assert "longer description" in result.description

    def test_args_with_types(self) -> None:
        doc = """\
Process data.

Args:
    name (str): The name of the item.
    count (int): How many items to process.
"""
        result = parse_docstring(doc)
        assert result.style == "google"
        assert len(result.params) == 2
        assert result.params[0].name == "name"
        assert result.params[0].type == "str"
        assert result.params[0].description == "The name of the item."
        assert result.params[1].name == "count"
        assert result.params[1].type == "int"

    def test_args_without_types(self) -> None:
        doc = """\
Process data.

Args:
    name: The name of the item.
    count: How many items.
"""
        result = parse_docstring(doc)
        assert result.style == "google"
        assert len(result.params) == 2
        assert result.params[0].name == "name"
        assert result.params[0].type is None
        assert result.params[0].description == "The name of the item."

    def test_multiline_param_description(self) -> None:
        doc = """\
Process data.

Args:
    name (str): The name of the item which
        can span multiple lines and be
        quite long indeed.
    count (int): Simple count.
"""
        result = parse_docstring(doc)
        assert len(result.params) == 2
        assert "span multiple lines" in result.params[0].description
        assert "quite long indeed" in result.params[0].description
        assert result.params[1].name == "count"

    def test_returns_section(self) -> None:
        doc = """\
Get the value.

Returns:
    str: The string representation.
"""
        result = parse_docstring(doc)
        assert result.style == "google"
        assert result.returns is not None
        assert result.returns.type == "str"
        assert result.returns.description == "The string representation."

    def test_returns_without_type(self) -> None:
        doc = """\
Get the value.

Returns:
    The computed result.
"""
        result = parse_docstring(doc)
        assert result.returns is not None
        assert result.returns.description == "The computed result."

    def test_raises_section(self) -> None:
        doc = """\
Process data.

Raises:
    ValueError: If the input is invalid.
    TypeError: If the type is wrong.
"""
        result = parse_docstring(doc)
        assert result.style == "google"
        assert len(result.raises) == 2
        assert result.raises[0].exception == "ValueError"
        assert result.raises[0].description == "If the input is invalid."
        assert result.raises[1].exception == "TypeError"

    def test_examples_section(self) -> None:
        doc = """\
Process data.

Examples:
    >>> process("hello")
    'HELLO'
    >>> process("world")
    'WORLD'
"""
        result = parse_docstring(doc)
        assert result.style == "google"
        assert len(result.examples) >= 1
        assert ">>> process" in result.examples[0].code

    def test_full_combined_docstring(self) -> None:
        doc = """\
Process the input data.

This function takes raw input and processes it according
to the specified rules.

Args:
    data (str): The input data to process.
    mode (int): The processing mode.

Returns:
    list[str]: The processed results.

Raises:
    ValueError: If data is empty.

Examples:
    >>> process("test", 1)
    ['TEST']

Notes:
    This is experimental.
"""
        result = parse_docstring(doc)
        assert result.style == "google"
        assert result.summary == "Process the input data."
        assert "raw input" in result.description
        assert len(result.params) == 2
        assert result.returns is not None
        assert len(result.raises) == 1
        assert len(result.examples) >= 1
        assert result.notes == "This is experimental."

    def test_attributes_section(self) -> None:
        doc = """\
A data container.

Attributes:
    name (str): The name.
    value (int): The value.
"""
        result = parse_docstring(doc)
        assert result.style == "google"
        assert len(result.params) == 2
        assert result.params[0].name == "name"
        assert result.params[1].name == "value"


# ===================================================================
# NumPy style tests
# ===================================================================


class TestNumpyStyle:
    """Tests for NumPy-style docstring parsing."""

    def test_simple_summary(self) -> None:
        doc = """\
Compute the sum.

Parameters
----------
    a : int
        First value.
"""
        result = parse_docstring(doc)
        assert result.style == "numpy"
        assert result.summary == "Compute the sum."

    def test_parameters_with_types(self) -> None:
        doc = """\
Compute result.

Parameters
----------
    x : float
        The x coordinate.
    y : float
        The y coordinate.
"""
        result = parse_docstring(doc)
        assert result.style == "numpy"
        assert len(result.params) == 2
        assert result.params[0].name == "x"
        assert result.params[0].type == "float"
        assert result.params[0].description == "The x coordinate."
        assert result.params[1].name == "y"
        assert result.params[1].type == "float"

    def test_returns_section(self) -> None:
        doc = """\
Compute distance.

Returns
-------
    float
        The euclidean distance.
"""
        result = parse_docstring(doc)
        assert result.returns is not None
        assert result.returns.type == "float"
        assert "euclidean distance" in result.returns.description

    def test_multiple_parameters(self) -> None:
        doc = """\
Add numbers.

Parameters
----------
    a : int
        First number.
    b : int
        Second number.
    c : int
        Third number.
"""
        result = parse_docstring(doc)
        assert len(result.params) == 3
        names = [p.name for p in result.params]
        assert names == ["a", "b", "c"]

    def test_notes_section(self) -> None:
        doc = """\
Do computation.

Parameters
----------
    x : int
        Value.

Notes
-----
    This uses a special algorithm.
"""
        result = parse_docstring(doc)
        assert "special algorithm" in result.notes

    def test_full_combined_docstring(self) -> None:
        doc = """\
Calculate weighted average.

Takes a list of values and weights and computes
the weighted arithmetic mean.

Parameters
----------
    values : list[float]
        The values to average.
    weights : list[float]
        The weights for each value.

Returns
-------
    float
        The weighted average.

Raises
------
    ValueError
        If lengths do not match.

Notes
-----
    Sum of weights must not be zero.
"""
        result = parse_docstring(doc)
        assert result.style == "numpy"
        assert result.summary == "Calculate weighted average."
        assert "weighted arithmetic mean" in result.description
        assert len(result.params) == 2
        assert result.returns is not None
        assert result.returns.type == "float"
        assert len(result.raises) == 1
        assert result.raises[0].exception == "ValueError"
        assert "weights must not be zero" in result.notes


# ===================================================================
# Sphinx style tests
# ===================================================================


class TestSphinxStyle:
    """Tests for Sphinx (reST) style docstring parsing."""

    def test_param_and_type_separate(self) -> None:
        doc = """\
Get item by name.

:param name: The item name.
:type name: str
"""
        result = parse_docstring(doc)
        assert result.style == "sphinx"
        assert len(result.params) == 1
        assert result.params[0].name == "name"
        assert result.params[0].type == "str"
        assert result.params[0].description == "The item name."

    def test_param_only(self) -> None:
        doc = """\
Set value.

:param value: The new value.
"""
        result = parse_docstring(doc)
        assert result.style == "sphinx"
        assert len(result.params) == 1
        assert result.params[0].name == "value"
        assert result.params[0].type is None

    def test_returns_and_rtype(self) -> None:
        doc = """\
Get total.

:returns: The total count.
:rtype: int
"""
        result = parse_docstring(doc)
        assert result.style == "sphinx"
        assert result.returns is not None
        assert result.returns.description == "The total count."
        assert result.returns.type == "int"

    def test_raises(self) -> None:
        doc = """\
Validate input.

:raises ValueError: If input is invalid.
"""
        result = parse_docstring(doc)
        assert result.style == "sphinx"
        assert len(result.raises) == 1
        assert result.raises[0].exception == "ValueError"
        assert result.raises[0].description == "If input is invalid."

    def test_multiple_params(self) -> None:
        doc = """\
Move object.

:param x: X position.
:type x: float
:param y: Y position.
:type y: float
:param z: Z position.
:type z: float
"""
        result = parse_docstring(doc)
        assert len(result.params) == 3
        assert result.params[0].name == "x"
        assert result.params[2].name == "z"
        assert result.params[1].type == "float"

    def test_full_combined_docstring(self) -> None:
        doc = """\
Process the file.

Reads and processes the given file path.

:param path: Path to the file.
:type path: str
:param encoding: File encoding.
:type encoding: str
:returns: The file contents.
:rtype: str
:raises FileNotFoundError: If the file does not exist.
"""
        result = parse_docstring(doc)
        assert result.style == "sphinx"
        assert result.summary == "Process the file."
        assert "Reads and processes" in result.description
        assert len(result.params) == 2
        assert result.returns is not None
        assert result.returns.type == "str"
        assert len(result.raises) == 1
        assert result.raises[0].exception == "FileNotFoundError"


# ===================================================================
# Auto-detection tests
# ===================================================================


class TestAutoDetection:
    """Tests for style auto-detection."""

    def test_detects_google(self) -> None:
        doc = """\
Summary.

Args:
    x: Value.
"""
        result = parse_docstring(doc)
        assert result.style == "google"

    def test_detects_numpy(self) -> None:
        doc = """\
Summary.

Parameters
----------
    x : int
        Value.
"""
        result = parse_docstring(doc)
        assert result.style == "numpy"

    def test_detects_sphinx(self) -> None:
        doc = """\
Summary.

:param x: Value.
"""
        result = parse_docstring(doc)
        assert result.style == "sphinx"

    def test_falls_back_to_unknown(self) -> None:
        doc = "Just a plain text description without any special sections."
        result = parse_docstring(doc)
        assert result.style == "unknown"
        assert result.summary == "Just a plain text description without any special sections."

    def test_numpy_priority_over_google(self) -> None:
        """NumPy with underlines should be detected even if 'Returns:' appears."""
        doc = """\
Summary.

Parameters
----------
    x : int
        Value.

Returns
-------
    int
        Result.
"""
        result = parse_docstring(doc)
        assert result.style == "numpy"


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_string(self) -> None:
        result = parse_docstring("")
        assert isinstance(result, ParsedDocstring)
        assert result.summary == ""
        assert result.style == "unknown"
        assert result.raw == ""

    def test_whitespace_only(self) -> None:
        result = parse_docstring("   \n   \n   ")
        assert result.summary == ""
        assert result.style == "unknown"

    def test_summary_only_no_sections(self) -> None:
        result = parse_docstring("Do the thing.")
        assert result.summary == "Do the thing."
        assert result.params == []
        assert result.returns is None

    def test_malformed_google_sections(self) -> None:
        doc = """\
Summary.

Args:
    not a proper param line
    also bad
"""
        # Should not crash
        result = parse_docstring(doc)
        assert result.style == "google"
        assert result.summary == "Summary."

    def test_unicode_content(self) -> None:
        doc = """\
Berechne die Summe.

Args:
    wert (float): Der Eingabewert fur die Berechnung.
"""
        result = parse_docstring(doc)
        assert result.style == "google"
        assert result.summary == "Berechne die Summe."
        assert result.params[0].name == "wert"

    def test_explicit_style_override(self) -> None:
        """When style is explicitly set, it should be used regardless."""
        doc = """\
Summary.

:param x: Value.
"""
        # Force google parsing on a sphinx-style doc
        result = parse_docstring(doc, style="google")
        assert result.style == "google"
        # It won't find Args: section, so params should be empty
        assert result.params == []

    def test_raw_preserved(self) -> None:
        doc = "  Summary line.\n\n  More details.\n"
        result = parse_docstring(doc)
        # raw should contain the (dedented) docstring
        assert result.raw != ""
        assert "Summary line." in result.raw

    def test_indented_docstring(self) -> None:
        """Typical real-world docstring with leading indentation."""
        doc = """    Process the data.

    Takes input and does something.

    Args:
        x (int): The value.
    """
        result = parse_docstring(doc)
        assert result.style == "google"
        assert result.summary == "Process the data."
        assert len(result.params) == 1
        assert result.params[0].name == "x"

    def test_notes_section_google(self) -> None:
        doc = """\
Do work.

Note:
    This is important to know.
"""
        result = parse_docstring(doc)
        assert result.style == "google"
        assert "important to know" in result.notes

    def test_examples_with_doctest(self) -> None:
        doc = """\
Add numbers.

Examples:
    >>> add(1, 2)
    3
    >>> add(0, 0)
    0
"""
        result = parse_docstring(doc)
        assert len(result.examples) >= 1
        assert ">>> add(1, 2)" in result.examples[0].code

    def test_returns_section_google_no_type(self) -> None:
        """Returns section with only a description, no type prefix."""
        doc = """\
Get thing.

Returns:
    The thing we wanted.
"""
        result = parse_docstring(doc)
        assert result.returns is not None
        assert result.returns.description == "The thing we wanted."
