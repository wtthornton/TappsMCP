"""Tests for docs_mcp.generators.api_docs — API documentation generator.

Covers data models, format rendering (markdown, mkdocs, sphinx RST),
depth filtering, cross-reference resolution, example extraction,
coverage calculation, and the ``docs_generate_api`` MCP tool handler.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from docs_mcp.generators.api_docs import (
    APIDocClass,
    APIDocFunction,
    APIDocGenerator,
    APIDocModule,
    APIDocParam,
    _extract_doctest,
    _find_function_end,
    _full_description,
    _generation_date,
    _is_noise_constant,
)
from tests.helpers import make_settings as _make_settings

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

SAMPLE_MODULE_NO_DOCS = """\
class Bare:
    x = 1

    def do_something(self, a, b):
        return a + b

def bare_func(x):
    return x * 2

SOME_CONST = 99
"""


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
            "def test_compute():\n    from mylib import compute\n    assert compute(5) == 10\n",
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
            "def test_compute():\n    assert True\n",
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

    async def test_success_response_envelope(self, tmp_path: Path) -> None:
        """Successful generation returns standard envelope."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "lib.py").write_text(SAMPLE_MODULE, encoding="utf-8")

        from docs_mcp.server_gen_tools import docs_generate_api

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_api(
                source_path="lib.py",
                format="markdown",
                depth="public",
                project_root=str(root),
            )

        assert result["success"] is True
        assert result["tool"] == "docs_generate_api"
        assert result["elapsed_ms"] >= 0
        assert "data" in result
        data = result["data"]
        assert data["format"] == "markdown"
        assert data["depth"] == "public"
        assert data["content_length"] > 0
        assert "written_to" in data

    async def test_invalid_root_returns_error(self, tmp_path: Path) -> None:
        """Non-existent project root returns an error."""
        fake = tmp_path / "no_such_dir"

        from docs_mcp.server_gen_tools import docs_generate_api

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(fake),
        ):
            result = await docs_generate_api(project_root=str(fake))

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    async def test_source_not_found_returns_error(self, tmp_path: Path) -> None:
        """Non-existent source_path returns SOURCE_NOT_FOUND error."""
        root = tmp_path / "proj"
        root.mkdir()

        from docs_mcp.server_gen_tools import docs_generate_api

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_api(
                source_path="nonexistent.py",
                project_root=str(root),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "SOURCE_NOT_FOUND"

    async def test_no_content_returns_error(self, tmp_path: Path) -> None:
        """A non-Python file produces NO_CONTENT error."""
        root = tmp_path / "proj"
        root.mkdir()
        (root / "readme.txt").write_text("hello", encoding="utf-8")

        from docs_mcp.server_gen_tools import docs_generate_api

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_api(
                source_path="readme.txt",
                project_root=str(root),
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


# ---------------------------------------------------------------------------
# Sample with full docstrings (Epic 15)
# ---------------------------------------------------------------------------

SAMPLE_FULL_DOCSTRINGS = '''\
"""Module with full multi-line docstrings."""

import structlog

logger = structlog.get_logger(__name__)

__all__ = ["process_data"]
__version__ = "1.0.0"


class DataProcessor:
    """Processes data through a configurable pipeline.

    This class provides a high-level interface for data processing.
    It supports multiple input formats and can be configured with
    custom transformers.

    Args:
        name: Processor name for identification.
    """

    def process(self, data: str) -> dict[str, int]:
        """Process the input data and return statistics.

        Takes a string, splits it into tokens, and returns a
        frequency count dictionary. Useful for text analysis.

        Args:
            data: The input text to process.

        Returns:
            dict[str, int]: A mapping from token to frequency count.

        Raises:
            ValueError: If data is empty.

        Examples:
            >>> processor = DataProcessor()
            >>> processor.process("hello world")
            {"hello": 1, "world": 1}
        """
        if not data:
            raise ValueError("empty data")
        tokens = data.split()
        return {t: tokens.count(t) for t in set(tokens)}

    def _internal_method(self, x: int) -> int:
        """Internal helper that doubles the value.

        Args:
            x: The input value.

        Returns:
            int: The doubled value.
        """
        return x * 2


def analyze(text: str, *, threshold: float = 0.5) -> list[str]:
    """Analyze text and return significant tokens.

    Performs frequency analysis on the input text and filters
    tokens below the given threshold. This is the main entry
    point for text analysis.

    Args:
        text: The input text to analyze.
        threshold: Minimum frequency ratio to include a token.

    Returns:
        list[str]: Tokens meeting the threshold.
    """
    return text.split()


def _private_with_docs() -> None:
    """A private function with documentation."""
    pass


def _private_no_docs() -> None:
    pass


MY_CONSTANT: int = 42
'''


# ---------------------------------------------------------------------------
# 13. TestFullDocstrings (Story 15.1)
# ---------------------------------------------------------------------------


class TestFullDocstrings:
    """Test that full docstring body is included, not just summary."""

    def test_full_description_helper_summary_only(self) -> None:
        """_full_description returns summary when no body present."""
        from docs_mcp.extractors.docstring_parser import ParsedDocstring

        parsed = ParsedDocstring(summary="Short summary.")
        result = _full_description(parsed)
        assert result == "Short summary."

    def test_full_description_helper_with_body(self) -> None:
        """_full_description combines summary + description."""
        from docs_mcp.extractors.docstring_parser import ParsedDocstring

        parsed = ParsedDocstring(
            summary="Short summary.",
            description="Extended body with more details.",
        )
        result = _full_description(parsed)
        assert "Short summary." in result
        assert "Extended body with more details." in result
        assert "\n\n" in result

    def test_full_description_empty_parsed(self) -> None:
        """_full_description returns empty for non-ParsedDocstring."""
        assert _full_description("not a parsed docstring") == ""

    def test_function_description_includes_body(self, tmp_path: Path) -> None:
        """Generated API docs include full docstring body for functions."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(source, project_root=tmp_path)

        # The analyze function has a body beyond the summary
        assert "Performs frequency analysis" in result

    def test_class_description_includes_body(self, tmp_path: Path) -> None:
        """Generated API docs include full docstring body for classes."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(source, project_root=tmp_path)

        # DataProcessor has extended description
        assert "custom transformers" in result

    def test_method_description_includes_body(self, tmp_path: Path) -> None:
        """Generated API docs include full docstring body for methods."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(source, project_root=tmp_path, depth="all")

        # DataProcessor.process has extended body
        assert "frequency count dictionary" in result


# ---------------------------------------------------------------------------
# 14. TestReturnType (Story 15.2)
# ---------------------------------------------------------------------------


class TestReturnType:
    """Test that return type annotations are rendered in API docs."""

    def test_return_type_field_on_model(self) -> None:
        """APIDocFunction has return_type field."""
        func = APIDocFunction(
            name="foo",
            signature="def foo() -> str",
            return_type="str",
        )
        assert func.return_type == "str"

    def test_return_type_default_empty(self) -> None:
        """return_type defaults to empty string."""
        func = APIDocFunction(name="foo", signature="def foo()")
        assert func.return_type == ""

    def test_return_type_in_markdown_output(self, tmp_path: Path) -> None:
        """Markdown output includes return type annotation."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(source, project_root=tmp_path)

        # analyze returns list[str], should appear in output
        assert "`list[str]`" in result

    def test_return_type_in_rst_output(self, tmp_path: Path) -> None:
        """RST output includes :rtype: from annotation."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(
            source,
            project_root=tmp_path,
            output_format="sphinx_rst",
        )

        assert ":rtype: list[str]" in result


# ---------------------------------------------------------------------------
# 15. TestNoiseFiltering (Story 15.4)
# ---------------------------------------------------------------------------


class TestNoiseFiltering:
    """Test that logger constants and noise are filtered from API docs."""

    def test_logger_filtered_by_name(self) -> None:
        assert _is_noise_constant("logger", "structlog.get_logger()") is True
        assert _is_noise_constant("LOG", None) is True
        assert _is_noise_constant("LOGGER", None) is True

    def test_logger_filtered_by_value(self) -> None:
        assert _is_noise_constant("my_log", "logging.getLogger(__name__)") is True

    def test_dunder_all_filtered(self) -> None:
        assert _is_noise_constant("__all__", '["foo"]') is True

    def test_dunder_version_filtered(self) -> None:
        assert _is_noise_constant("__version__", '"1.0.0"') is True

    def test_normal_constant_not_filtered(self) -> None:
        assert _is_noise_constant("MAX_RETRIES", "3") is False
        assert _is_noise_constant("MY_CONSTANT", "42") is False

    def test_logger_not_in_generated_docs(self, tmp_path: Path) -> None:
        """Logger constant should not appear in generated API docs."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(source, project_root=tmp_path, depth="all")

        # logger should be filtered
        assert "| `logger`" not in result
        assert "| `__all__`" not in result
        assert "| `__version__`" not in result
        # But regular constant should remain
        assert "MY_CONSTANT" in result


# ---------------------------------------------------------------------------
# 16. TestIncludePrivate (Story 15.4)
# ---------------------------------------------------------------------------


class TestIncludePrivate:
    """Test include_private option for documented private functions."""

    def test_private_excluded_by_default(self, tmp_path: Path) -> None:
        """Private functions excluded in public depth by default."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(source, project_root=tmp_path)

        assert "_private_with_docs" not in result
        assert "_private_no_docs" not in result

    def test_include_private_shows_documented_privates(self, tmp_path: Path) -> None:
        """include_private=True shows private functions WITH docstrings."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(
            source,
            project_root=tmp_path,
            include_private=True,
        )

        assert "_private_with_docs" in result
        # _private_no_docs has no docstring, should still be excluded
        assert "_private_no_docs" not in result

    def test_should_include_symbol_private_with_docstring(self) -> None:
        """_should_include_symbol includes documented private when flagged."""
        assert (
            APIDocGenerator._should_include_symbol(
                "_helper",
                "public",
                True,
                "Has docs",
            )
            is True
        )

    def test_should_include_symbol_private_no_docstring(self) -> None:
        """_should_include_symbol excludes undocumented private even when flagged."""
        assert (
            APIDocGenerator._should_include_symbol(
                "_helper",
                "public",
                True,
                None,
            )
            is False
        )

    def test_should_include_symbol_public_unaffected(self) -> None:
        """_should_include_symbol does not affect public symbols."""
        assert (
            APIDocGenerator._should_include_symbol(
                "public_func",
                "public",
                False,
                None,
            )
            is True
        )


# ---------------------------------------------------------------------------
# 17. TestEnhancedExamples (Story 15.5)
# ---------------------------------------------------------------------------


class TestEnhancedExamples:
    """Test enhanced example extraction (doctest patterns)."""

    def test_extract_doctest_finds_pattern(self) -> None:
        """_extract_doctest finds >>> func_name patterns."""
        content = """\
Some text.

    >>> my_func(1, 2)
    3
    >>> my_func(0, 0)
    0

More text.
"""
        result = _extract_doctest(content, "my_func")
        assert ">>> my_func(1, 2)" in result
        assert "3" in result

    def test_extract_doctest_no_match(self) -> None:
        """_extract_doctest returns empty when function not found."""
        content = ">>> other_func()\nresult"
        assert _extract_doctest(content, "my_func") == ""

    def test_extract_doctest_continuation(self) -> None:
        """_extract_doctest includes ... continuation lines."""
        content = """\
    >>> result = my_func(
    ...     long_arg="value",
    ... )
    True
"""
        result = _extract_doctest(content, "my_func")
        assert ">>> result = my_func(" in result
        assert '...     long_arg="value",' in result

    def test_max_examples_increased(self) -> None:
        """_MAX_EXAMPLES is now 5 (was 2)."""
        from docs_mcp.generators.api_docs import _MAX_EXAMPLES

        assert _MAX_EXAMPLES == 5

    def test_finds_examples_in_test_dir(self, tmp_path: Path) -> None:
        """Example finder checks both 'tests' and 'test' directories."""
        source = tmp_path / "mod.py"
        source.write_text(
            'def my_func():\n    """Do something."""\n    pass\n',
            encoding="utf-8",
        )

        # Create test dir (not tests)
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        test_file = test_dir / "test_mod.py"
        test_file.write_text(
            "def test_my_func():\n    result = my_func()\n    assert result\n",
            encoding="utf-8",
        )

        gen = APIDocGenerator()
        result = gen.generate(source, project_root=tmp_path)

        assert "test_my_func" in result


# ---------------------------------------------------------------------------
# 18. TestReExportDetection (Story 17.1)
# ---------------------------------------------------------------------------


SAMPLE_REEXPORT_MODULE = '''\
"""Package init that re-exports symbols."""

from .core import process
from .models import Config

__all__ = ["process", "Config"]
'''

SAMPLE_INIT_WITH_DEFS = '''\
"""Package with its own definitions."""

class Registry:
    """Central registry."""
    pass

def setup():
    """Set up the package."""
    pass
'''


class TestReExportDetection:
    """Test re-export module detection."""

    def test_is_reexport_init_no_defs(self, tmp_path: Path) -> None:
        """__init__.py with no functions/classes is detected as re-export."""
        init = tmp_path / "__init__.py"
        init.write_text(SAMPLE_REEXPORT_MODULE, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(init, project_root=tmp_path)

        assert "re-exports symbols" in result

    def test_init_with_defs_not_reexport(self, tmp_path: Path) -> None:
        """__init__.py with original defs is NOT a re-export."""
        init = tmp_path / "__init__.py"
        init.write_text(SAMPLE_INIT_WITH_DEFS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(init, project_root=tmp_path)

        assert "re-exports symbols" not in result

    def test_regular_module_not_reexport(self, tmp_path: Path) -> None:
        """Regular .py file is never a re-export."""
        mod = tmp_path / "core.py"
        mod.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(mod, project_root=tmp_path)

        assert "re-exports symbols" not in result

    def test_is_reexport_field_on_model(self) -> None:
        """APIDocModule has is_reexport field."""
        m = APIDocModule(name="test", is_reexport=True)
        assert m.is_reexport is True


# ---------------------------------------------------------------------------
# 19. TestFreshnessHints (Story 17.3)
# ---------------------------------------------------------------------------


class TestFreshnessHints:
    """Test documentation freshness hints in generated output."""

    def test_generation_date_in_output(self, tmp_path: Path) -> None:
        """Generated docs include auto-generation date."""
        source = tmp_path / "mod.py"
        source.write_text(SAMPLE_FULL_DOCSTRINGS, encoding="utf-8")

        gen = APIDocGenerator()
        result = gen.generate(source, project_root=tmp_path)

        assert "Auto-generated by DocsMCP on" in result

    def test_generation_date_format(self) -> None:
        """_generation_date returns ISO date string."""
        date = _generation_date()
        assert len(date) == 10  # YYYY-MM-DD
        assert date.count("-") == 2


# ---------------------------------------------------------------------------
# 20. TestQualityMetrics (Story 17.4)
# ---------------------------------------------------------------------------


class TestQualityMetrics:
    """Test documentation quality metrics in generated output."""

    def test_quality_fields_on_model(self) -> None:
        """APIDocModule has quality metric fields."""
        m = APIDocModule(
            name="test",
            total_public=5,
            documented_count=3,
            missing_returns=2,
            missing_examples=4,
        )
        assert m.total_public == 5
        assert m.documented_count == 3
        assert m.missing_returns == 2
        assert m.missing_examples == 4

    def test_quality_notes_in_markdown(self, tmp_path: Path) -> None:
        """Generated docs include quality notes when functions lack returns."""
        source = tmp_path / "mod.py"
        source.write_text(
            'def foo():\n    """No return doc."""\n    pass\n\n'
            'def bar():\n    """Also no return.\n\n    Returns:\n        str: A value.\n    """\n    return "x"\n',
            encoding="utf-8",
        )

        gen = APIDocGenerator()
        result = gen.generate(source, project_root=tmp_path)

        assert "missing return docs" in result or "missing examples" in result
