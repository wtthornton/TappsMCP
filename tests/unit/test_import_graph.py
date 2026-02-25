"""Tests for the import graph builder."""

from __future__ import annotations

from tapps_mcp.project.import_graph import (
    ImportEdge,
    ImportGraph,
    _extract_imports,
    _file_to_module,
    build_import_graph,
)

# ---------------------------------------------------------------------------
# _file_to_module
# ---------------------------------------------------------------------------


class TestFileToModule:
    def test_simple_module(self, tmp_path):
        """Simple .py file maps to dotted module name."""
        project_root = tmp_path
        file_path = tmp_path / "mypkg" / "utils.py"
        result = _file_to_module(file_path, project_root, "mypkg")
        assert result == "mypkg.utils"

    def test_nested_module(self, tmp_path):
        """Nested .py file maps correctly."""
        project_root = tmp_path
        file_path = tmp_path / "mypkg" / "sub" / "deep.py"
        result = _file_to_module(file_path, project_root, "mypkg")
        assert result == "mypkg.sub.deep"

    def test_init_file(self, tmp_path):
        """__init__.py maps to its parent package name."""
        project_root = tmp_path
        file_path = tmp_path / "mypkg" / "__init__.py"
        result = _file_to_module(file_path, project_root, "mypkg")
        assert result == "mypkg"

    def test_init_file_nested(self, tmp_path):
        """Nested __init__.py maps to the sub-package."""
        project_root = tmp_path
        file_path = tmp_path / "mypkg" / "sub" / "__init__.py"
        result = _file_to_module(file_path, project_root, "mypkg")
        assert result == "mypkg.sub"

    def test_src_layout(self, tmp_path):
        """src/ prefix is stripped when top_level is specified."""
        project_root = tmp_path
        file_path = tmp_path / "src" / "mypkg" / "core.py"
        result = _file_to_module(file_path, project_root, "mypkg")
        assert result == "mypkg.core"

    def test_outside_root_returns_empty(self, tmp_path):
        """File outside project root returns empty string."""
        project_root = tmp_path / "project"
        file_path = tmp_path / "other" / "file.py"
        result = _file_to_module(file_path, project_root, "")
        assert result == ""


# ---------------------------------------------------------------------------
# _extract_imports
# ---------------------------------------------------------------------------


class TestExtractImports:
    def test_basic_import(self, tmp_path):
        """Simple import statement is extracted."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        a_file = pkg / "a.py"
        a_file.write_text("import mypkg.b\n")
        (pkg / "b.py").write_text("")

        project_modules = {"mypkg", "mypkg.a", "mypkg.b"}
        edges, externals = _extract_imports(a_file, "mypkg.a", project_modules)

        assert len(edges) == 1
        assert edges[0].source_module == "mypkg.a"
        assert edges[0].target_module == "mypkg.b"
        assert edges[0].import_type == "runtime"

    def test_from_import(self, tmp_path):
        """from ... import ... statement is extracted."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        a_file = pkg / "a.py"
        a_file.write_text("from mypkg.b import something\n")
        (pkg / "b.py").write_text("")

        project_modules = {"mypkg", "mypkg.a", "mypkg.b"}
        edges, externals = _extract_imports(a_file, "mypkg.a", project_modules)

        assert len(edges) == 1
        assert edges[0].target_module == "mypkg.b"

    def test_relative_import(self, tmp_path):
        """Relative imports are resolved correctly."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        a_file = pkg / "a.py"
        a_file.write_text("from . import b\n")
        (pkg / "b.py").write_text("")

        project_modules = {"mypkg", "mypkg.a", "mypkg.b"}
        edges, externals = _extract_imports(a_file, "mypkg.a", project_modules)

        assert len(edges) == 1
        assert edges[0].target_module == "mypkg.b"

    def test_type_checking_import(self, tmp_path):
        """Imports inside TYPE_CHECKING blocks are classified."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        a_file = pkg / "a.py"
        a_file.write_text(
            "from typing import TYPE_CHECKING\n"
            "\n"
            "if TYPE_CHECKING:\n"
            "    from mypkg.b import MyClass\n"
        )
        (pkg / "b.py").write_text("")

        project_modules = {"mypkg", "mypkg.a", "mypkg.b"}
        edges, externals = _extract_imports(a_file, "mypkg.a", project_modules)

        assert len(edges) == 1
        assert edges[0].import_type == "type_checking"

    def test_try_except_import(self, tmp_path):
        """Imports inside try/except ImportError are conditional."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        a_file = pkg / "a.py"
        a_file.write_text(
            "try:\n    from mypkg.b import optional\nexcept ImportError:\n    optional = None\n"
        )
        (pkg / "b.py").write_text("")

        project_modules = {"mypkg", "mypkg.a", "mypkg.b"}
        edges, externals = _extract_imports(a_file, "mypkg.a", project_modules)

        assert len(edges) == 1
        assert edges[0].import_type == "conditional"

    def test_stdlib_ignored(self, tmp_path):
        """Standard library imports are not included in edges or externals."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        a_file = pkg / "a.py"
        a_file.write_text("import os\nimport sys\nfrom pathlib import Path\n")

        project_modules = {"mypkg", "mypkg.a"}
        edges, externals = _extract_imports(a_file, "mypkg.a", project_modules)

        assert len(edges) == 0
        assert len(externals) == 0

    def test_syntax_error_returns_empty(self, tmp_path):
        """Files with syntax errors return no edges."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        bad_file = pkg / "bad.py"
        bad_file.write_text("def broken(\n")

        project_modules = {"mypkg", "mypkg.bad"}
        edges, externals = _extract_imports(bad_file, "mypkg.bad", project_modules)

        assert edges == []
        assert externals == set()

    def test_external_import_detected(self, tmp_path):
        """Third-party imports appear in the externals set."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        a_file = pkg / "a.py"
        a_file.write_text("import requests\nfrom flask import Flask\n")

        project_modules = {"mypkg", "mypkg.a"}
        edges, externals = _extract_imports(a_file, "mypkg.a", project_modules)

        assert len(edges) == 0
        assert "requests" in externals
        assert "flask" in externals


# ---------------------------------------------------------------------------
# build_import_graph
# ---------------------------------------------------------------------------


class TestBuildImportGraph:
    def test_simple_graph(self, tmp_path):
        """Build graph from a simple two-module project."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("from mypkg.b import something\n")
        (pkg / "b.py").write_text("import mypkg.a\n")

        graph = build_import_graph(tmp_path, top_level_package="mypkg")

        assert len(graph.edges) == 2
        assert "mypkg.a" in graph.modules
        assert "mypkg.b" in graph.modules
        assert "mypkg" in graph.modules

    def test_excludes_patterns(self, tmp_path):
        """Excluded directories are skipped."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("")

        excluded = tmp_path / "mypkg" / "vendor"
        excluded.mkdir()
        (excluded / "__init__.py").write_text("")
        (excluded / "lib.py").write_text("from mypkg.a import X\n")

        graph = build_import_graph(
            tmp_path,
            top_level_package="mypkg",
            exclude_patterns=["vendor"],
        )

        module_names = {e.source_module for e in graph.edges}
        assert "mypkg.vendor.lib" not in module_names
        assert "mypkg.vendor.lib" not in graph.modules

    def test_pb2_files_excluded(self, tmp_path):
        """Protobuf generated files (_pb2.py) are excluded."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "message_pb2.py").write_text("import mypkg\n")
        (pkg / "a.py").write_text("")

        graph = build_import_graph(tmp_path, top_level_package="mypkg")

        assert "mypkg.message_pb2" not in graph.modules

    def test_project_root_stored(self, tmp_path):
        """Graph stores the project root."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")

        graph = build_import_graph(tmp_path, top_level_package="mypkg")

        assert graph.project_root == str(tmp_path)

    def test_empty_project(self, tmp_path):
        """Empty project yields an empty graph."""
        graph = build_import_graph(tmp_path, top_level_package="mypkg")

        assert len(graph.edges) == 0
        assert len(graph.modules) == 0


# ---------------------------------------------------------------------------
# ImportGraph methods
# ---------------------------------------------------------------------------


class TestImportGraphMethods:
    def test_get_dependencies(self):
        """get_dependencies returns efferent edges."""
        graph = ImportGraph(
            edges=[
                ImportEdge(source_module="a", target_module="b"),
                ImportEdge(source_module="a", target_module="c"),
                ImportEdge(source_module="b", target_module="c"),
            ],
            modules={"a", "b", "c"},
        )

        deps = graph.get_dependencies("a")
        assert sorted(deps) == ["b", "c"]

    def test_get_dependents(self):
        """get_dependents returns afferent edges."""
        graph = ImportGraph(
            edges=[
                ImportEdge(source_module="a", target_module="c"),
                ImportEdge(source_module="b", target_module="c"),
            ],
            modules={"a", "b", "c"},
        )

        dependents = graph.get_dependents("c")
        assert sorted(dependents) == ["a", "b"]

    def test_get_dependencies_empty(self):
        """Module with no dependencies returns empty list."""
        graph = ImportGraph(
            edges=[ImportEdge(source_module="a", target_module="b")],
            modules={"a", "b"},
        )

        assert graph.get_dependencies("b") == []

    def test_get_dependents_empty(self):
        """Module with no dependents returns empty list."""
        graph = ImportGraph(
            edges=[ImportEdge(source_module="a", target_module="b")],
            modules={"a", "b"},
        )

        assert graph.get_dependents("a") == []
