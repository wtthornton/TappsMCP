"""Tests for the public API surface detector."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer


@pytest.fixture
def analyzer() -> APISurfaceAnalyzer:
    """Create a fresh analyzer instance."""
    return APISurfaceAnalyzer()


# ---------------------------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------------------------


class TestBasicExtraction:
    """Tests for basic function, class, and constant extraction."""

    def test_public_function_detected(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Public functions appear in the API surface."""
        src = tmp_path / "mod.py"
        src.write_text(
            'def greet(name: str) -> str:\n    """Say hello."""\n    return f"hi {name}"\n'
        )
        surface = analyzer.analyze(src)
        assert len(surface.functions) == 1
        assert surface.functions[0].name == "greet"
        assert surface.functions[0].return_type == "str"
        assert surface.functions[0].docstring_present is True

    def test_public_class_detected(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Public classes appear with method counts."""
        src = tmp_path / "mod.py"
        src.write_text(
            'class Widget:\n    """A widget."""\n'
            "    def run(self) -> None: ...\n"
            "    def stop(self) -> None: ...\n"
            "    def _reset(self) -> None: ...\n"
        )
        surface = analyzer.analyze(src)
        assert len(surface.classes) == 1
        cls = surface.classes[0]
        assert cls.name == "Widget"
        assert cls.docstring_present is True
        assert cls.method_count == 3
        assert cls.public_methods == ["run", "stop"]

    def test_public_constant_detected(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Public constants appear in the API surface."""
        src = tmp_path / "mod.py"
        src.write_text("MAX_SIZE: int = 100\nDEFAULT_NAME = 'world'\n")
        surface = analyzer.analyze(src)
        assert len(surface.constants) == 2
        names = {c.name for c in surface.constants}
        assert names == {"MAX_SIZE", "DEFAULT_NAME"}
        typed = next(c for c in surface.constants if c.name == "MAX_SIZE")
        assert typed.type == "int"
        assert typed.value == "100"

    def test_async_function_in_surface(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Async functions are flagged correctly."""
        src = tmp_path / "mod.py"
        src.write_text('async def fetch(url: str) -> bytes:\n    """Fetch data."""\n    ...\n')
        surface = analyzer.analyze(src)
        assert len(surface.functions) == 1
        assert surface.functions[0].is_async is True
        assert surface.functions[0].name == "fetch"

    def test_decorated_function_in_surface(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Decorators are captured on public functions."""
        src = tmp_path / "mod.py"
        src.write_text(
            "import functools\n"
            "@functools.cache\n"
            'def expensive() -> int:\n    """Cached computation."""\n    return 42\n'
        )
        surface = analyzer.analyze(src)
        assert len(surface.functions) == 1
        assert "functools.cache" in surface.functions[0].decorators

    def test_function_parameters_extracted(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Function parameters include name, type, and default."""
        src = tmp_path / "mod.py"
        src.write_text(
            "def connect(host: str, port: int = 8080) -> None:\n"
            '    """Connect to server."""\n    ...\n'
        )
        surface = analyzer.analyze(src)
        func = surface.functions[0]
        assert len(func.parameters) == 2
        host_param = func.parameters[0]
        assert host_param["name"] == "host"
        assert host_param["type"] == "str"
        assert host_param["default"] is None
        port_param = func.parameters[1]
        assert port_param["name"] == "port"
        assert port_param["type"] == "int"
        assert port_param["default"] == "8080"


# ---------------------------------------------------------------------------
# Visibility rules
# ---------------------------------------------------------------------------


class TestVisibilityRules:
    """Tests for public/private/protected filtering."""

    def test_private_names_excluded(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Names starting with _ are excluded by default."""
        src = tmp_path / "mod.py"
        src.write_text("def public() -> None: ...\ndef _private() -> None: ...\n_INTERNAL = 42\n")
        surface = analyzer.analyze(src)
        assert len(surface.functions) == 1
        assert surface.functions[0].name == "public"
        assert len(surface.constants) == 0

    def test_dunder_names_excluded(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Dunder names like __version__ are excluded from constants."""
        src = tmp_path / "mod.py"
        src.write_text("__version__ = '1.0.0'\nVERSION = '1.0.0'\n")
        surface = analyzer.analyze(src)
        names = [c.name for c in surface.constants]
        assert "__version__" not in names
        assert "VERSION" in names

    def test_all_overrides_private_included(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """A private name listed in __all__ IS included."""
        src = tmp_path / "mod.py"
        src.write_text(
            "__all__ = ['_helper', 'public_func']\n"
            "def _helper() -> None: ...\n"
            "def public_func() -> None: ...\n"
            "def other() -> None: ...\n"
        )
        surface = analyzer.analyze(src)
        names = {f.name for f in surface.functions}
        assert names == {"_helper", "public_func"}

    def test_all_overrides_public_excluded(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """A public name NOT in __all__ is excluded."""
        src = tmp_path / "mod.py"
        src.write_text("__all__ = ['keep']\ndef keep() -> None: ...\ndef skip() -> None: ...\n")
        surface = analyzer.analyze(src)
        names = {f.name for f in surface.functions}
        assert names == {"keep"}

    def test_depth_protected_includes_underscore(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """depth='protected' includes single-underscore names."""
        src = tmp_path / "mod.py"
        src.write_text("def public() -> None: ...\ndef _protected() -> None: ...\n__dunder__ = 1\n")
        surface = analyzer.analyze(src, depth="protected")
        func_names = {f.name for f in surface.functions}
        assert "public" in func_names
        assert "_protected" in func_names

    def test_depth_all_includes_everything(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """depth='all' includes private and dunder names."""
        src = tmp_path / "mod.py"
        src.write_text(
            "def public() -> None: ...\n"
            "def _private() -> None: ...\n"
            "def __dunder__() -> None: ...\n"
        )
        surface = analyzer.analyze(src, depth="all")
        func_names = {f.name for f in surface.functions}
        assert func_names == {"public", "_private", "__dunder__"}


# ---------------------------------------------------------------------------
# Coverage calculation
# ---------------------------------------------------------------------------


class TestCoverageCalculation:
    """Tests for docstring coverage metrics."""

    def test_full_coverage(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """All public names documented -> coverage = 1.0."""
        src = tmp_path / "mod.py"
        src.write_text(
            'def foo() -> None:\n    """Documented."""\n    ...\n\n'
            'class Bar:\n    """Documented."""\n    ...\n'
        )
        surface = analyzer.analyze(src)
        assert surface.coverage == 1.0
        assert surface.missing_docs == []

    def test_no_coverage(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """No docstrings -> coverage = 0.0."""
        src = tmp_path / "mod.py"
        src.write_text("def foo() -> None: ...\n\nclass Bar: ...\n")
        surface = analyzer.analyze(src)
        assert surface.coverage == 0.0
        assert set(surface.missing_docs) == {"foo", "Bar"}

    def test_partial_coverage(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Half documented -> coverage = 0.5."""
        src = tmp_path / "mod.py"
        src.write_text(
            'def documented() -> None:\n    """Has docs."""\n    ...\n\n'
            "def undocumented() -> None: ...\n"
        )
        surface = analyzer.analyze(src)
        assert surface.coverage == pytest.approx(0.5)
        assert surface.missing_docs == ["undocumented"]

    def test_constants_only_coverage(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Module with only constants still gets coverage 1.0 (no eligible items)."""
        src = tmp_path / "mod.py"
        src.write_text("MAX = 100\nMIN = 0\n")
        surface = analyzer.analyze(src)
        # Constants are not docstring-eligible, so coverage is 1.0 when there are public names
        assert surface.coverage == 1.0
        assert surface.total_public == 2


# ---------------------------------------------------------------------------
# Missing docs
# ---------------------------------------------------------------------------


class TestMissingDocs:
    """Tests for missing documentation tracking."""

    def test_missing_docs_lists_undocumented(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Undocumented public names appear in missing_docs."""
        src = tmp_path / "mod.py"
        src.write_text(
            'def no_doc() -> None: ...\ndef has_doc() -> None:\n    """Present."""\n    ...\n'
        )
        surface = analyzer.analyze(src)
        assert "no_doc" in surface.missing_docs
        assert "has_doc" not in surface.missing_docs

    def test_empty_missing_docs_when_all_documented(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """All documented -> missing_docs is empty."""
        src = tmp_path / "mod.py"
        src.write_text(
            'def a() -> None:\n    """Doc a."""\n    ...\n\n'
            'def b() -> None:\n    """Doc b."""\n    ...\n'
        )
        surface = analyzer.analyze(src)
        assert surface.missing_docs == []


# ---------------------------------------------------------------------------
# Re-exports
# ---------------------------------------------------------------------------


class TestReExports:
    """Tests for re-export detection in __init__.py files."""

    def test_init_re_exports_detected(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """__init__.py with relative imports detects re-exports."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        init = pkg / "__init__.py"
        init.write_text("from .core import Engine\nfrom .utils import helper\n")
        # Need sub-modules for the imports to make sense structurally,
        # but the detector only parses the init file itself
        surface = analyzer.analyze(init)
        assert "Engine" in surface.re_exports
        assert "helper" in surface.re_exports

    def test_regular_file_no_re_exports(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Non-__init__.py files have no re-exports."""
        src = tmp_path / "regular.py"
        src.write_text("from .other import Thing\ndef foo(): ...\n")
        surface = analyzer.analyze(src)
        assert surface.re_exports == []

    def test_re_export_with_alias(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """'from .sub import X as Y' uses the alias Y."""
        pkg = tmp_path / "pkg"
        pkg.mkdir()
        init = pkg / "__init__.py"
        init.write_text("from .internal import _impl as public_api\n")
        surface = analyzer.analyze(init)
        assert "public_api" in surface.re_exports


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_file(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Empty file produces empty API surface."""
        src = tmp_path / "empty.py"
        src.write_text("")
        surface = analyzer.analyze(src)
        assert surface.functions == []
        assert surface.classes == []
        assert surface.constants == []
        assert surface.total_public == 0

    def test_only_private_names(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """File with only private names has empty public API."""
        src = tmp_path / "mod.py"
        src.write_text("def _helper() -> None: ...\n_INTERNAL = 42\nclass _Base: ...\n")
        surface = analyzer.analyze(src)
        assert surface.functions == []
        assert surface.classes == []
        assert surface.constants == []
        assert surface.total_public == 0

    def test_nonexistent_file(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Nonexistent file returns empty surface without crashing."""
        missing = tmp_path / "does_not_exist.py"
        surface = analyzer.analyze(missing)
        assert surface.functions == []
        assert surface.classes == []
        assert surface.total_public == 0
        assert surface.source_path == str(missing)

    def test_syntax_error_file(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """File with syntax errors returns empty surface without crashing."""
        src = tmp_path / "bad.py"
        src.write_text("def broken(\n")
        surface = analyzer.analyze(src)
        assert surface.total_public == 0

    def test_all_exports_stored(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """The __all__ list is preserved on the surface."""
        src = tmp_path / "mod.py"
        src.write_text(
            "__all__ = ['alpha', 'beta']\n"
            "def alpha() -> None: ...\n"
            "def beta() -> None: ...\n"
            "def gamma() -> None: ...\n"
        )
        surface = analyzer.analyze(src)
        assert surface.all_exports == ["alpha", "beta"]

    def test_class_bases_captured(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Inheritance bases are captured on API classes."""
        src = tmp_path / "mod.py"
        src.write_text('class Child(Base, Mixin):\n    """A child class."""\n    ...\n')
        surface = analyzer.analyze(src)
        assert surface.classes[0].bases == ["Base", "Mixin"]

    def test_docstring_summary_extracted(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Docstring summary is extracted for functions."""
        src = tmp_path / "mod.py"
        src.write_text(
            "def process(data: list) -> list:\n"
            '    """Process the input data.\n\n'
            "    This function does important things.\n"
            '    """\n'
            "    return data\n"
        )
        surface = analyzer.analyze(src)
        assert surface.functions[0].docstring_summary == "Process the input data."

    def test_total_public_count(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """total_public counts all public names."""
        src = tmp_path / "mod.py"
        src.write_text(
            "MAX = 10\ndef foo() -> None: ...\nclass Bar: ...\ndef _skip() -> None: ...\n"
        )
        surface = analyzer.analyze(src)
        assert surface.total_public == 3  # MAX, foo, Bar

    def test_type_alias_detected(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """Type aliases using Union/Optional are detected."""
        src = tmp_path / "mod.py"
        src.write_text("from typing import Union\nResult = Union[str, int]\n")
        surface = analyzer.analyze(src)
        assert "Result" in surface.type_aliases

    def test_source_path_relative(
        self,
        analyzer: APISurfaceAnalyzer,
        tmp_path: Path,
    ) -> None:
        """source_path is relative when project_root is provided."""
        src = tmp_path / "pkg" / "mod.py"
        src.parent.mkdir()
        src.write_text("X = 1\n")
        surface = analyzer.analyze(src, project_root=tmp_path)
        # PythonExtractor makes path relative to project_root
        assert not surface.source_path.startswith(str(tmp_path))
