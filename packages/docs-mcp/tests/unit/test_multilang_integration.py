"""Integration tests for multi-language analyzer support (Epic 12).

Verifies that APISurfaceAnalyzer and ModuleMapAnalyzer correctly use
the dispatcher to handle non-Python source files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer
from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

# Fixtures live alongside tests, one level up.
_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

HAS_TREE_SITTER = False
try:
    import tree_sitter  # noqa: F401

    HAS_TREE_SITTER = True
except ImportError:
    pass

needs_treesitter = pytest.mark.skipif(
    not HAS_TREE_SITTER,
    reason="tree-sitter not installed",
)


# ---------------------------------------------------------------------------
# APISurfaceAnalyzer -- multi-language dispatch
# ---------------------------------------------------------------------------


class TestAPISurfaceDispatchPython:
    """APISurfaceAnalyzer works for Python without an explicit extractor."""

    def test_python_file_analyzed(self, tmp_path: Path) -> None:
        py_file = tmp_path / "example.py"
        py_file.write_text(
            'def greet(name: str) -> str:\n    """Say hello."""\n    return f"hello {name}"\n'
        )
        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(py_file)
        assert len(surface.functions) == 1
        assert surface.functions[0].name == "greet"

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(tmp_path / "missing.py")
        assert surface.total_public == 0


@needs_treesitter
class TestAPISurfaceDispatchTypeScript:
    """APISurfaceAnalyzer dispatches .ts files to TypeScriptExtractor."""

    def test_ts_functions_extracted(self) -> None:
        ts_file = _FIXTURES_DIR / "sample.ts"
        assert ts_file.exists(), f"Fixture missing: {ts_file}"

        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(ts_file)
        func_names = {f.name for f in surface.functions}
        assert "greet" in func_names

    def test_ts_classes_extracted(self) -> None:
        ts_file = _FIXTURES_DIR / "sample.ts"
        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(ts_file)
        class_names = {c.name for c in surface.classes}
        assert len(class_names) >= 1


@needs_treesitter
class TestAPISurfaceDispatchGo:
    """APISurfaceAnalyzer dispatches .go files to GoExtractor."""

    def test_go_functions_extracted(self) -> None:
        go_file = _FIXTURES_DIR / "sample.go"
        assert go_file.exists()

        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(go_file)
        func_names = {f.name for f in surface.functions}
        assert len(func_names) >= 1

    def test_go_classes_are_structs(self) -> None:
        go_file = _FIXTURES_DIR / "sample.go"
        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(go_file)
        # Go structs map to classes in the extractor model.
        assert len(surface.classes) >= 1


@needs_treesitter
class TestAPISurfaceDispatchRust:
    """APISurfaceAnalyzer dispatches .rs files to RustExtractor."""

    def test_rust_functions_extracted(self) -> None:
        rs_file = _FIXTURES_DIR / "sample.rs"
        assert rs_file.exists()

        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(rs_file)
        func_names = {f.name for f in surface.functions}
        assert len(func_names) >= 1

    def test_rust_structs_extracted(self) -> None:
        rs_file = _FIXTURES_DIR / "sample.rs"
        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(rs_file)
        class_names = {c.name for c in surface.classes}
        assert len(class_names) >= 1


@needs_treesitter
class TestAPISurfaceDispatchJava:
    """APISurfaceAnalyzer dispatches .java files to JavaExtractor."""

    def test_java_classes_extracted(self) -> None:
        java_file = _FIXTURES_DIR / "sample.java"
        assert java_file.exists()

        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(java_file)
        class_names = {c.name for c in surface.classes}
        assert len(class_names) >= 1


# ---------------------------------------------------------------------------
# APISurfaceAnalyzer -- graceful fallback without tree-sitter
# ---------------------------------------------------------------------------


class TestAPISurfaceFallback:
    """When tree-sitter is unavailable, GenericExtractor is used."""

    def test_unknown_extension_still_works(self, tmp_path: Path) -> None:
        """An unrecognised extension falls through to GenericExtractor."""
        file = tmp_path / "code.lua"
        file.write_text("function hello()\n  print('hello')\nend\n")

        analyzer = APISurfaceAnalyzer()
        surface = analyzer.analyze(file)
        # GenericExtractor may or may not find anything — but no crash.
        assert surface.source_path is not None


# ---------------------------------------------------------------------------
# ModuleMapAnalyzer -- multi-language file discovery
# ---------------------------------------------------------------------------


class TestModuleMapMultiLang:
    """ModuleMapAnalyzer picks up non-Python source files."""

    def test_discovers_python_files(self, tmp_path: Path) -> None:
        pkg = tmp_path / "mypackage"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "core.py").write_text("def main() -> None:\n    pass\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)
        names = {n.name for n in result.module_tree[0].submodules}
        assert "core" in names

    @needs_treesitter
    def test_discovers_ts_files(self, tmp_path: Path) -> None:
        (tmp_path / "index.ts").write_text("export function hello(): string { return 'hi'; }\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)
        names = {n.name for n in result.module_tree}
        assert "index" in names

    @needs_treesitter
    def test_discovers_go_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.go").write_text("package main\n\nfunc main() {}\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)
        names = {n.name for n in result.module_tree}
        assert "main" in names

    @needs_treesitter
    def test_discovers_rust_files(self, tmp_path: Path) -> None:
        (tmp_path / "lib.rs").write_text("pub fn init() {}\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)
        names = {n.name for n in result.module_tree}
        assert "lib" in names

    @needs_treesitter
    def test_discovers_java_files(self, tmp_path: Path) -> None:
        (tmp_path / "App.java").write_text("public class App {}\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)
        names = {n.name for n in result.module_tree}
        assert "App" in names

    def test_mixed_language_project(self, tmp_path: Path) -> None:
        """Python files are always found, other languages gracefully degrade."""
        (tmp_path / "server.py").write_text("def serve() -> None:\n    pass\n")
        (tmp_path / "client.ts").write_text("export function connect() {}\n")
        (tmp_path / "helpers.go").write_text("package helpers\n\nfunc Help() {}\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)
        names = {n.name for n in result.module_tree}
        assert "server" in names
        # Non-Python files found regardless (tree-sitter or GenericExtractor).
        assert "client" in names
        assert "helpers" in names


# ---------------------------------------------------------------------------
# Language composition in docs_project_scan
# ---------------------------------------------------------------------------


class TestCountSourceFiles:
    """Verify the _count_source_files helper works correctly."""

    def test_counts_python(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "readme.md").write_text("")

        from docs_mcp.server import _count_source_files

        counts = _count_source_files(tmp_path)
        assert counts.get("Python") == 2
        assert "Markdown" not in counts  # .md is not a source file

    def test_counts_multi_language(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("")
        (tmp_path / "app.ts").write_text("")
        (tmp_path / "lib.go").write_text("")
        (tmp_path / "core.rs").write_text("")
        (tmp_path / "Main.java").write_text("")

        from docs_mcp.server import _count_source_files

        counts = _count_source_files(tmp_path)
        assert counts["Python"] == 1
        assert counts["TypeScript"] == 1
        assert counts["Go"] == 1
        assert counts["Rust"] == 1
        assert counts["Java"] == 1

    def test_skips_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "app.ts").write_text("")
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "dep.ts").write_text("")

        from docs_mcp.server import _count_source_files

        counts = _count_source_files(tmp_path)
        assert counts.get("TypeScript") == 1  # Only the root file

    def test_empty_directory(self, tmp_path: Path) -> None:
        from docs_mcp.server import _count_source_files

        counts = _count_source_files(tmp_path)
        assert counts == {}
