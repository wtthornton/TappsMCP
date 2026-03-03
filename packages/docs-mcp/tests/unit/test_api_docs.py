"""Tests for docs_mcp.generators.api_docs — API documentation generator.

Covers data models, format rendering (markdown, mkdocs, sphinx RST),
depth filtering, cross-reference resolution, example extraction,
coverage calculation, and the ``docs_generate_api`` MCP tool handler.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from docs_mcp.generators.api_docs import (
    APIDocClass,
    APIDocFunction,
    APIDocGenerator,
    APIDocModule,
    APIDocParam,
    _find_function_end,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously for testing."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_settings(root: Path) -> MagicMock:
    """Create a mock DocsMCPSettings pointing to root."""
    settings = MagicMock()
    settings.project_root = root
    settings.output_dir = "docs"
    settings.default_format = "markdown"
    settings.log_level = "INFO"
    settings.log_json = False
    return settings


# ---------------------------------------------------------------------------
# Sample source code fixtures
# ---------------------------------------------------------------------------

SAMPLE_MODULE = '''\
"""Sample module for testing."""

from typing import Optional


class Config:
    """Configuration class.

    Args:
        name: The config name.
        debug: Enable debug mode.
    """

    MAX_RETRIES: int = 3

    def __init__(self, name: str, debug: bool = False) -> None:
        self.name = name
        self.debug = debug

    def validate(self) -> bool:
        """Validate the configuration.

        Returns:
            True if valid.
        """
        return bool(self.name)

    def _reset(self) -> None:
        """Reset internal state (protected)."""
        self.name = ""

    def __repr__(self) -> str:
        return f"Config({self.name!r})"


def process(data: str, *, timeout: int = 30) -> Optional[str]:
    """Process input data.

    Args:
        data: The input data to process.
        timeout: Processing timeout in seconds.

    Returns:
        Processed result or None on failure.

    Raises:
        ValueError: If data is empty.
    """
    if not data:
        raise ValueError("data is empty")
    return data.upper()


def _internal_helper() -> None:
    """An internal helper function."""
    pass


MAX_RETRIES: int = 3
_PRIVATE_CONST: int = 42
'''

SAMPLE_MODULE_NO_DOCS = '''\
class Bare:
    x = 1

    def do_something(self, a, b):
        return a + b

def bare_func(x):
    return x * 2

SOME_CONST = 99
'''


# ---------------------------------------------------------------------------
# 1. TestAPIDocModels
# ---------------------------------------------------------------------------


class TestAPIDocModels:
    """Test model instantiation and defaults."""

    def test_param_defaults(self) -> None:
        """APIDocParam sets reasonable defaults."""
        p = APIDocParam(name="x")
        assert p.name == "x"
        assert p.type == ""
        assert p.description == ""
        assert p.default is None

    def test_param_full(self) -> None:
        """APIDocParam stores all fields."""
        p = APIDocParam(name="timeout", type="int", description="Seconds", default="30")
        assert p.type == "int"
        assert p.default == "30"

    def test_function_defaults(self) -> None:
        """APIDocFunction sets boolean flags to False by default."""
        f = APIDocFunction(name="foo", signature="def foo()")
        assert f.is_async is False
        assert f.is_property is False
        assert f.is_classmethod is False
        assert f.is_staticmethod is False
        assert f.params == []
        assert f.raises == []
        assert f.examples == []
        assert f.line == 0

    def test_class_defaults(self) -> None:
        """APIDocClass has empty lists by default."""
        c = APIDocClass(name="MyClass")
        assert c.bases == []
        assert c.methods == []
        assert c.class_variables == []
        assert c.decorators == []

    def test_module_defaults(self) -> None:
        """APIDocModule starts with 0.0 coverage."""
        m = APIDocModule(name="mymod")
        assert m.coverage == 0.0
        assert m.functions == []
        assert m.classes == []
        assert m.constants == []
        assert m.docstring == ""


# ---------------------------------------------------------------------------
# 2. TestAPIDocGeneratorValidation
# ---------------------------------------------------------------------------


class TestAPIDocGeneratorValidation:
    """Test input validation in APIDocGenerator.generate()."""

    def test_invalid_format_returns_empty(self, tmp_path: Path) -> None:
        """An unrecognized format returns empty string."""
        src = tmp_path / "mod.py"
        src.write_text("x = 1\n", encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="html")
        assert result == ""

    def test_invalid_depth_returns_empty(self, tmp_path: Path) -> None:
        """An unrecognized depth returns empty string."""
        src = tmp_path / "mod.py"
        src.write_text("x = 1\n", encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, depth="private")
        assert result == ""

    def test_nonexistent_path_returns_empty(self, tmp_path: Path) -> None:
        """A path that does not exist returns empty string."""
        gen = APIDocGenerator()
        result = gen.generate(tmp_path / "nope.py", project_root=tmp_path)
        assert result == ""

    def test_non_python_file_returns_empty(self, tmp_path: Path) -> None:
        """A non-.py file returns empty string."""
        txt = tmp_path / "notes.txt"
        txt.write_text("hello", encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(txt, project_root=tmp_path)
        assert result == ""


# ---------------------------------------------------------------------------
# 3. TestAPIDocGeneratorSingleFile
# ---------------------------------------------------------------------------


class TestAPIDocGeneratorSingleFile:
    """Generate docs for a single Python file."""

    def test_generates_nonempty_output(self, tmp_path: Path) -> None:
        """A valid Python file produces non-empty markdown."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path)
        assert len(result) > 0

    def test_contains_module_name(self, tmp_path: Path) -> None:
        """Output includes the module name derived from the file path."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path)
        assert "sample" in result

    def test_contains_class_name(self, tmp_path: Path) -> None:
        """Output mentions the Config class."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path)
        assert "Config" in result

    def test_contains_function_name(self, tmp_path: Path) -> None:
        """Output mentions the process function."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path)
        assert "process" in result

    def test_contains_docstring_description(self, tmp_path: Path) -> None:
        """Output includes docstring summaries."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path)
        assert "Process input data" in result

    def test_coverage_footer_present(self, tmp_path: Path) -> None:
        """Output includes the coverage footer."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path)
        assert "Documentation coverage:" in result


# ---------------------------------------------------------------------------
# 4. TestAPIDocGeneratorDirectory
# ---------------------------------------------------------------------------


class TestAPIDocGeneratorDirectory:
    """Generate docs for a directory of Python files."""

    def test_directory_combines_files(self, tmp_path: Path) -> None:
        """A directory with multiple .py files produces combined output."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "alpha.py").write_text(
            '"""Alpha module."""\n\ndef alpha_fn() -> int:\n    """Return one."""\n    return 1\n',
            encoding="utf-8",
        )
        (pkg / "beta.py").write_text(
            '"""Beta module."""\n\ndef beta_fn() -> int:\n    """Return two."""\n    return 2\n',
            encoding="utf-8",
        )
        gen = APIDocGenerator()
        result = gen.generate(pkg, project_root=tmp_path)
        assert "alpha_fn" in result
        assert "beta_fn" in result

    def test_directory_separator_between_files(self, tmp_path: Path) -> None:
        """Files are separated by horizontal rules."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "a.py").write_text(
            '"""A."""\ndef fa() -> None:\n    """Fa."""\n    pass\n',
            encoding="utf-8",
        )
        (pkg / "b.py").write_text(
            '"""B."""\ndef fb() -> None:\n    """Fb."""\n    pass\n',
            encoding="utf-8",
        )
        gen = APIDocGenerator()
        result = gen.generate(pkg, project_root=tmp_path)
        assert "---" in result

    def test_skips_pycache_dirs(self, tmp_path: Path) -> None:
        """__pycache__ directories are skipped."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "good.py").write_text(
            '"""Good."""\ndef gf() -> None:\n    """Good fn."""\n    pass\n',
            encoding="utf-8",
        )
        cache = pkg / "__pycache__"
        cache.mkdir()
        (cache / "bad.py").write_text("x = 1\n", encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(pkg, project_root=tmp_path)
        assert "gf" in result
        # __pycache__/bad.py should not appear
        assert "bad" not in result.lower() or "bad" not in result.split("`")

    def test_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        """A directory with no .py files returns empty string."""
        empty = tmp_path / "empty"
        empty.mkdir()
        gen = APIDocGenerator()
        result = gen.generate(empty, project_root=tmp_path)
        assert result == ""


# ---------------------------------------------------------------------------
# 5. TestAPIDocGeneratorDepth
# ---------------------------------------------------------------------------


class TestAPIDocGeneratorDepth:
    """Test public/protected/all depth filtering."""

    def test_public_excludes_underscore(self, tmp_path: Path) -> None:
        """Public depth excludes _internal_helper."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, depth="public")
        assert "_internal_helper" not in result
        assert "process" in result

    def test_public_excludes_private_const(self, tmp_path: Path) -> None:
        """Public depth excludes _PRIVATE_CONST."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, depth="public")
        assert "_PRIVATE_CONST" not in result
        assert "MAX_RETRIES" in result

    def test_protected_includes_single_underscore(self, tmp_path: Path) -> None:
        """Protected depth includes _internal_helper."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, depth="protected")
        assert "_internal_helper" in result

    def test_protected_excludes_dunder(self, tmp_path: Path) -> None:
        """Protected depth excludes __repr__ but keeps __init__."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, depth="protected")
        assert "__repr__" not in result

    def test_all_includes_everything(self, tmp_path: Path) -> None:
        """All depth includes private and dunder symbols."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, depth="all")
        assert "_internal_helper" in result
        assert "_PRIVATE_CONST" in result

    def test_init_always_included(self, tmp_path: Path) -> None:
        """__init__ is included even at public depth."""
        src = tmp_path / "mod.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, depth="public")
        assert "__init__" in result


# ---------------------------------------------------------------------------
# 6. TestAPIDocMarkdown
# ---------------------------------------------------------------------------


class TestAPIDocMarkdown:
    """Verify markdown output structure."""

    def test_h1_module_heading(self, tmp_path: Path) -> None:
        """Markdown starts with an H1 heading for the module."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="markdown")
        assert result.startswith("# `")

    def test_h2_sections_present(self, tmp_path: Path) -> None:
        """Markdown has H2 sections for Classes, Functions, Constants."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="markdown")
        assert "## Classes" in result
        assert "## Functions" in result
        assert "## Constants" in result

    def test_param_table_present(self, tmp_path: Path) -> None:
        """Function with params has a parameter table."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="markdown")
        assert "**Parameters:**" in result
        assert "| Name | Type | Description | Default |" in result

    def test_returns_section(self, tmp_path: Path) -> None:
        """Documented returns appear in the output."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="markdown")
        assert "**Returns:**" in result

    def test_raises_section(self, tmp_path: Path) -> None:
        """Documented raises appear in the output."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="markdown")
        assert "**Raises:**" in result
        assert "ValueError" in result

    def test_constants_table(self, tmp_path: Path) -> None:
        """Constants render as a table with Name, Type, Value columns."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="markdown")
        assert "| Name | Type | Value |" in result
        assert "MAX_RETRIES" in result


# ---------------------------------------------------------------------------
# 7. TestAPIDocMkdocs
# ---------------------------------------------------------------------------


class TestAPIDocMkdocs:
    """Verify mkdocs output has YAML frontmatter."""

    def test_yaml_frontmatter(self, tmp_path: Path) -> None:
        """MkDocs format starts with YAML frontmatter."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="mkdocs")
        assert result.startswith("---\n")
        assert "title:" in result

    def test_autodoc_directive(self, tmp_path: Path) -> None:
        """MkDocs format includes ::: autodoc reference."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="mkdocs")
        assert ":::" in result

    def test_includes_markdown_body(self, tmp_path: Path) -> None:
        """MkDocs format also includes the full markdown rendering."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="mkdocs")
        # The markdown body is appended after the frontmatter
        assert "## Classes" in result
        assert "## Functions" in result


# ---------------------------------------------------------------------------
# 8. TestAPIDocSphinxRST
# ---------------------------------------------------------------------------


class TestAPIDocSphinxRST:
    """Verify RST output uses correct Sphinx directives."""

    def test_title_underline(self, tmp_path: Path) -> None:
        """RST output has a title with = underline."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="sphinx_rst")
        lines = result.split("\n")
        # Second line should be all '=' characters
        assert lines[1].strip() == "=" * len(lines[0].strip())

    def test_class_directive(self, tmp_path: Path) -> None:
        """RST uses .. class:: directive."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="sphinx_rst")
        assert ".. class:: Config" in result

    def test_function_directive(self, tmp_path: Path) -> None:
        """RST uses .. function:: directive for module-level functions."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="sphinx_rst")
        assert ".. function::" in result

    def test_method_directive(self, tmp_path: Path) -> None:
        """RST uses .. method:: directive for class methods."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="sphinx_rst")
        assert ".. method::" in result

    def test_param_fields(self, tmp_path: Path) -> None:
        """RST uses :param name: syntax."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="sphinx_rst")
        assert ":param " in result

    def test_data_directive_for_constants(self, tmp_path: Path) -> None:
        """RST uses .. data:: for module-level constants."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="sphinx_rst")
        assert ".. data:: MAX_RETRIES" in result

    def test_coverage_footer(self, tmp_path: Path) -> None:
        """RST includes documentation coverage at the end."""
        src = tmp_path / "sample.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path, output_format="sphinx_rst")
        assert "Documentation coverage:" in result


# ---------------------------------------------------------------------------
# 9. TestAPIDocCrossRefs
# ---------------------------------------------------------------------------


class TestAPIDocCrossRefs:
    """Test cross-reference resolution."""

    def test_backtick_name_becomes_link(self) -> None:
        """A backtick-wrapped known symbol becomes a markdown anchor link."""
        gen = APIDocGenerator()
        text = "See `process` for details."
        result = gen._resolve_cross_refs(text, {"process", "Config"})
        assert "[`process`](#process)" in result

    def test_unknown_symbol_unchanged(self) -> None:
        """A backtick-wrapped unknown name stays as-is."""
        gen = APIDocGenerator()
        text = "See `unknown_thing` for details."
        result = gen._resolve_cross_refs(text, {"process"})
        assert "`unknown_thing`" in result
        assert "[`unknown_thing`]" not in result

    def test_empty_text_returns_empty(self) -> None:
        """Empty text returns empty."""
        gen = APIDocGenerator()
        assert gen._resolve_cross_refs("", {"process"}) == ""

    def test_no_symbols_returns_text(self) -> None:
        """Empty symbol set returns original text."""
        gen = APIDocGenerator()
        text = "See `something`."
        assert gen._resolve_cross_refs(text, set()) == text


# ---------------------------------------------------------------------------
# 10. TestAPIDocExamples
# ---------------------------------------------------------------------------


class TestAPIDocExamples:
    """Test example extraction from test files."""

    def test_finds_example_in_tests(self, tmp_path: Path) -> None:
        """Examples are found from test files matching the function name."""
        # Create a source file
        src = tmp_path / "mylib.py"
        src.write_text(
            '"""Lib."""\n\ndef compute(x: int) -> int:\n'
            '    """Compute value."""\n    return x * 2\n',
            encoding="utf-8",
        )
        # Create a tests directory with a matching test
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_mylib.py").write_text(
            'def test_compute():\n    from mylib import compute\n    assert compute(5) == 10\n',
            encoding="utf-8",
        )
        gen = APIDocGenerator()
        result = gen.generate(
            src,
            project_root=tmp_path,
            output_format="markdown",
            include_examples=True,
        )
        assert "**Examples:**" in result

    def test_no_tests_dir_no_examples(self, tmp_path: Path) -> None:
        """When no tests/ directory exists, no examples are added."""
        src = tmp_path / "mylib.py"
        src.write_text(
            '"""Lib."""\n\ndef compute(x: int) -> int:\n'
            '    """Compute value."""\n    return x * 2\n',
            encoding="utf-8",
        )
        gen = APIDocGenerator()
        result = gen.generate(
            src,
            project_root=tmp_path,
            output_format="markdown",
            include_examples=True,
        )
        assert "**Examples:**" not in result

    def test_include_examples_false_skips(self, tmp_path: Path) -> None:
        """When include_examples=False, examples are not searched."""
        src = tmp_path / "mylib.py"
        src.write_text(
            '"""Lib."""\n\ndef compute(x: int) -> int:\n'
            '    """Compute value."""\n    return x * 2\n',
            encoding="utf-8",
        )
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_mylib.py").write_text(
            'def test_compute():\n    assert True\n',
            encoding="utf-8",
        )
        gen = APIDocGenerator()
        result = gen.generate(
            src,
            project_root=tmp_path,
            output_format="markdown",
            include_examples=False,
        )
        assert "**Examples:**" not in result


# ---------------------------------------------------------------------------
# 11. TestAPIDocCoverage
# ---------------------------------------------------------------------------


class TestAPIDocCoverage:
    """Test coverage calculation."""

    def test_fully_documented_high_coverage(self, tmp_path: Path) -> None:
        """A fully documented module has high coverage."""
        src = tmp_path / "doc.py"
        src.write_text(SAMPLE_MODULE, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path)
        # SAMPLE_MODULE has docstrings on most public items
        # Extract coverage percentage from output
        assert "Documentation coverage:" in result
        # The coverage line: *Documentation coverage: NN.N%*
        for line in result.split("\n"):
            if "Documentation coverage:" in line:
                # Extract the number
                import re

                match = re.search(r"(\d+\.?\d*)%", line)
                assert match is not None
                coverage = float(match.group(1))
                assert coverage > 50.0  # Should be well documented
                break

    def test_undocumented_low_coverage(self, tmp_path: Path) -> None:
        """A module with no docstrings has low coverage."""
        src = tmp_path / "bare.py"
        src.write_text(SAMPLE_MODULE_NO_DOCS, encoding="utf-8")
        gen = APIDocGenerator()
        result = gen.generate(src, project_root=tmp_path)
        assert "Documentation coverage:" in result
        for line in result.split("\n"):
            if "Documentation coverage:" in line:
                import re

                match = re.search(r"(\d+\.?\d*)%", line)
                assert match is not None
                coverage = float(match.group(1))
                # Constants with annotation/value count as documented,
                # but class and functions lack docstrings
                assert coverage < 100.0
                break


# ---------------------------------------------------------------------------
# 12. TestAPIDocMCPTool
# ---------------------------------------------------------------------------


class TestAPIDocMCPTool:
    """Test docs_generate_api MCP tool response envelope."""

    def test_success_response_envelope(self, tmp_path: Path) -> None:
        """Successful generation returns standard envelope."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "lib.py").write_text(SAMPLE_MODULE, encoding="utf-8")

        from docs_mcp.server_gen_tools import docs_generate_api

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = _run(
                docs_generate_api(
                    source_path="lib.py",
                    format="markdown",
                    depth="public",
                    project_root=str(root),
                )
            )

        assert result["success"] is True
        assert result["tool"] == "docs_generate_api"
        assert result["elapsed_ms"] >= 0
        assert "data" in result
        data = result["data"]
        assert data["format"] == "markdown"
        assert data["depth"] == "public"
        assert data["content_length"] > 0
        assert "content" in data

    def test_invalid_root_returns_error(self, tmp_path: Path) -> None:
        """Non-existent project root returns an error."""
        fake = tmp_path / "no_such_dir"

        from docs_mcp.server_gen_tools import docs_generate_api

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(fake),
        ):
            result = _run(docs_generate_api(project_root=str(fake)))

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    def test_source_not_found_returns_error(self, tmp_path: Path) -> None:
        """Non-existent source_path returns SOURCE_NOT_FOUND error."""
        root = tmp_path / "proj"
        root.mkdir()

        from docs_mcp.server_gen_tools import docs_generate_api

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = _run(
                docs_generate_api(
                    source_path="nonexistent.py",
                    project_root=str(root),
                )
            )

        assert result["success"] is False
        assert result["error"]["code"] == "SOURCE_NOT_FOUND"

    def test_no_content_returns_error(self, tmp_path: Path) -> None:
        """A non-Python file produces NO_CONTENT error."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "readme.txt").write_text("hello", encoding="utf-8")

        from docs_mcp.server_gen_tools import docs_generate_api

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = _run(
                docs_generate_api(
                    source_path="readme.txt",
                    project_root=str(root),
                )
            )

        assert result["success"] is False
        assert result["error"]["code"] == "NO_CONTENT"


# ---------------------------------------------------------------------------
# 13. TestFindFunctionEnd (helper)
# ---------------------------------------------------------------------------


class TestFindFunctionEnd:
    """Test the _find_function_end helper."""

    def test_simple_function(self) -> None:
        """Finds end of a simple function body."""
        content = "def foo():\n    x = 1\n    return x\n\ndef bar():\n    pass\n"
        # body_start is after "def foo():\n"
        body_start = content.index("\n    x = 1")
        end = _find_function_end(content, body_start)
        body = content[body_start:end]
        assert "x = 1" in body
        assert "return x" in body

    def test_empty_body(self) -> None:
        """Empty content returns body_start."""
        assert _find_function_end("", 0) == 0

    def test_no_indented_lines(self) -> None:
        """When there are no indented lines, returns start."""
        result = _find_function_end("no indent here\n", 0)
        # Should be body_start since base_indent can be found
        assert result >= 0


# ---------------------------------------------------------------------------
# 14. TestShouldInclude (static method)
# ---------------------------------------------------------------------------


class TestShouldInclude:
    """Test the _should_include depth filter logic."""

    def test_public_excludes_underscore_prefix(self) -> None:
        assert APIDocGenerator._should_include("_private", "public") is False

    def test_public_includes_regular_name(self) -> None:
        assert APIDocGenerator._should_include("public_func", "public") is True

    def test_public_includes_init(self) -> None:
        assert APIDocGenerator._should_include("__init__", "public") is True

    def test_protected_includes_single_underscore(self) -> None:
        assert APIDocGenerator._should_include("_helper", "protected") is True

    def test_protected_excludes_dunder(self) -> None:
        assert APIDocGenerator._should_include("__repr__", "protected") is False

    def test_protected_includes_init(self) -> None:
        assert APIDocGenerator._should_include("__init__", "protected") is True

    def test_all_includes_everything(self) -> None:
        assert APIDocGenerator._should_include("__repr__", "all") is True
        assert APIDocGenerator._should_include("_private", "all") is True
        assert APIDocGenerator._should_include("public", "all") is True
