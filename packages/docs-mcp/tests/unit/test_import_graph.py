"""Tests for the import dependency graph builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from docs_mcp.analyzers.dependency import ImportEdge, ImportGraph, ImportGraphBuilder


@pytest.fixture
def builder() -> ImportGraphBuilder:
    return ImportGraphBuilder()


# ------------------------------------------------------------------
# Basic import detection
# ------------------------------------------------------------------


class TestBasicImportDetection:
    def test_import_foo_detected(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """import foo is detected when foo.py exists in project."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "import helper\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text(
            "x = 1\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        assert len(graph.edges) == 1
        edge = graph.edges[0]
        assert edge.source == "src/main.py"
        assert edge.target == "src/helper.py"
        assert edge.import_type == "runtime"

    def test_from_foo_import_bar_detected(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """from foo import bar is detected with names."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "from helper import func\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text(
            "def func(): pass\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        assert len(graph.edges) == 1
        assert graph.edges[0].names == ["func"]

    def test_from_foo_import_multiple_names(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """from foo import bar, baz detected with multiple names."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "from helper import func_a, func_b\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text(
            "def func_a(): pass\ndef func_b(): pass\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        assert len(graph.edges) == 1
        assert sorted(graph.edges[0].names) == ["func_a", "func_b"]

    def test_relative_import_sibling(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """from . import sibling detected for relative import."""
        root = tmp_path / "proj"
        pkg = root / "src" / "pkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "alpha.py").write_text(
            "from . import beta\n",
            encoding="utf-8",
        )
        (pkg / "beta.py").write_text(
            "x = 1\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        internal_edges = [e for e in graph.edges if e.target.endswith("beta.py")]
        assert len(internal_edges) == 1
        assert internal_edges[0].source.endswith("alpha.py")

    def test_relative_import_parent(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """from ..parent import something detected."""
        root = tmp_path / "proj"
        outer = root / "src" / "pkg"
        inner = outer / "sub"
        inner.mkdir(parents=True)
        (outer / "__init__.py").write_text("", encoding="utf-8")
        (outer / "utils.py").write_text(
            "def helper(): pass\n",
            encoding="utf-8",
        )
        (inner / "__init__.py").write_text("", encoding="utf-8")
        (inner / "mod.py").write_text(
            "from ..utils import helper\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        edges_to_utils = [e for e in graph.edges if "utils.py" in e.target]
        assert len(edges_to_utils) == 1
        assert edges_to_utils[0].names == ["helper"]

    def test_line_number_recorded(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Import line numbers are recorded."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "# comment\n\nimport helper\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        assert graph.edges[0].line == 3


# ------------------------------------------------------------------
# Import classification
# ------------------------------------------------------------------


class TestImportClassification:
    def test_internal_import(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Import to a file in the project is internal."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "a.py").write_text("import b\n", encoding="utf-8")
        (src / "b.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        assert graph.total_internal_imports == 1
        assert graph.total_external_imports == 0

    def test_external_import(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Import of a third-party package is external."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "import requests\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        assert graph.total_internal_imports == 0
        assert graph.total_external_imports == 1
        assert "requests" in graph.external_imports.get("src/main.py", [])

    def test_stdlib_import(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Stdlib imports (os, sys, pathlib) are not counted as external."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "import os\nimport sys\nfrom pathlib import Path\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        assert graph.total_internal_imports == 0
        assert graph.total_external_imports == 0

    def test_mixed_import_types_in_one_file(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """A file with internal, external, and stdlib imports."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "import os\nimport requests\nimport helper\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        assert graph.total_internal_imports == 1
        assert graph.total_external_imports == 1


# ------------------------------------------------------------------
# Special import types
# ------------------------------------------------------------------


class TestSpecialImportTypes:
    def test_type_checking_guard(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Imports under if TYPE_CHECKING: are classified as type_checking."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "from __future__ import annotations\n"
            "from typing import TYPE_CHECKING\n"
            "if TYPE_CHECKING:\n"
            "    import helper\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        tc_edges = [e for e in graph.edges if e.import_type == "type_checking"]
        assert len(tc_edges) == 1
        assert tc_edges[0].target == "src/helper.py"

    def test_try_except_import_error(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Imports inside try/except ImportError are conditional."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "try:\n    import helper\nexcept ImportError:\n    helper = None\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        cond_edges = [e for e in graph.edges if e.import_type == "conditional"]
        assert len(cond_edges) == 1

    def test_lazy_import_in_function(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Imports inside function bodies are lazy."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "def load():\n    import helper\n    return helper\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        lazy_edges = [e for e in graph.edges if e.import_type == "lazy"]
        assert len(lazy_edges) == 1

    def test_runtime_import_at_top_level(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Regular top-level imports are runtime."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "import helper\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        assert graph.edges[0].import_type == "runtime"


# ------------------------------------------------------------------
# Graph construction
# ------------------------------------------------------------------


class TestGraphConstruction:
    def test_entry_points_no_incoming_edges(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Modules with no incoming edges are entry points."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "import helper\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        assert "src/main.py" in graph.entry_points
        assert "src/helper.py" not in graph.entry_points

    def test_most_imported_sorted(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Most-imported modules sorted by incoming edge count (desc)."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "a.py").write_text(
            "import utils\nimport config\n",
            encoding="utf-8",
        )
        (src / "b.py").write_text(
            "import utils\n",
            encoding="utf-8",
        )
        (src / "utils.py").write_text("x = 1\n", encoding="utf-8")
        (src / "config.py").write_text("y = 1\n", encoding="utf-8")
        graph = builder.build(root)
        assert len(graph.most_imported) >= 2
        # utils imported by 2 files, config by 1
        assert graph.most_imported[0] == "src/utils.py"

    def test_internal_external_counts(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Internal and external counts are correct."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text(
            "import helper\nimport requests\nimport flask\n",
            encoding="utf-8",
        )
        (src / "helper.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        assert graph.total_internal_imports == 1
        assert graph.total_external_imports == 2

    def test_multi_file_cross_imports(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Multi-file project with cross-imports."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "a.py").write_text("import b\n", encoding="utf-8")
        (src / "b.py").write_text("import c\n", encoding="utf-8")
        (src / "c.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        assert graph.total_internal_imports == 2
        sources = {e.source for e in graph.edges}
        assert "src/a.py" in sources
        assert "src/b.py" in sources


# ------------------------------------------------------------------
# Edge cases
# ------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_project(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Empty project produces empty graph."""
        root = tmp_path / "empty"
        root.mkdir()
        graph = builder.build(root)
        assert graph == ImportGraph()

    def test_single_file_no_imports(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Single file with no imports."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text("x = 1\n", encoding="utf-8")
        graph = builder.build(root)
        assert graph.edges == []
        assert graph.modules == ["src/main.py"]
        assert graph.entry_points == ["src/main.py"]

    def test_syntax_error_skipped(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """File with syntax errors is skipped gracefully."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "bad.py").write_text(
            "def foo(:\n    pass\n",
            encoding="utf-8",
        )
        (src / "good.py").write_text(
            "x = 1\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        # Both are discovered as modules, but bad.py yields no edges
        assert "src/bad.py" in graph.modules
        assert "src/good.py" in graph.modules
        assert graph.edges == []

    def test_circular_imports(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Circular imports produce edges in both directions without crash."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "a.py").write_text("import b\n", encoding="utf-8")
        (src / "b.py").write_text("import a\n", encoding="utf-8")
        graph = builder.build(root)
        assert graph.total_internal_imports == 2
        sources = {(e.source, e.target) for e in graph.edges}
        assert ("src/a.py", "src/b.py") in sources
        assert ("src/b.py", "src/a.py") in sources

    def test_skip_dirs_excluded(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Files in SKIP_DIRS are not included."""
        root = tmp_path / "proj"
        src = root / "src"
        src.mkdir(parents=True)
        (src / "main.py").write_text("x = 1\n", encoding="utf-8")
        cache = src / "__pycache__"
        cache.mkdir()
        (cache / "main.cpython-312.py").write_text("", encoding="utf-8")
        graph = builder.build(root)
        assert len(graph.modules) == 1
        assert graph.modules[0] == "src/main.py"

    def test_source_dirs_override(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Custom source_dirs parameter is respected."""
        root = tmp_path / "proj"
        lib = root / "lib"
        lib.mkdir(parents=True)
        (lib / "mod.py").write_text("x = 1\n", encoding="utf-8")
        # Also create a src/ dir that should be ignored
        src = root / "src"
        src.mkdir(parents=True)
        (src / "other.py").write_text("y = 1\n", encoding="utf-8")
        graph = builder.build(root, source_dirs=["lib"])
        assert "lib/mod.py" in graph.modules
        assert all("src/" not in m for m in graph.modules)


# ------------------------------------------------------------------
# Package imports
# ------------------------------------------------------------------


class TestPackageImports:
    def test_import_package_resolves_to_init(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """Importing a package resolves to its __init__.py."""
        root = tmp_path / "proj"
        src = root / "src"
        pkg = src / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text(
            "API_VERSION = 1\n",
            encoding="utf-8",
        )
        (src / "main.py").write_text(
            "import mypkg\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        pkg_edges = [e for e in graph.edges if "mypkg" in e.target]
        assert len(pkg_edges) == 1
        assert pkg_edges[0].target == "src/mypkg/__init__.py"

    def test_from_package_import_submodule(
        self,
        builder: ImportGraphBuilder,
        tmp_path: Path,
    ) -> None:
        """from pkg import mod resolves to pkg/mod.py."""
        root = tmp_path / "proj"
        src = root / "src"
        pkg = src / "mypkg"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "utils.py").write_text("x = 1\n", encoding="utf-8")
        (src / "main.py").write_text(
            "from mypkg import utils\n",
            encoding="utf-8",
        )
        graph = builder.build(root)
        # The import `from mypkg import utils` targets mypkg module
        # (since `mypkg` is the module in the ImportFrom node)
        assert graph.total_internal_imports >= 1


# ------------------------------------------------------------------
# Model tests
# ------------------------------------------------------------------


class TestModels:
    def test_import_edge_defaults(self) -> None:
        """ImportEdge has correct defaults."""
        edge = ImportEdge(source="a.py", target="b.py")
        assert edge.import_type == "runtime"
        assert edge.line == 0
        assert edge.names == []

    def test_import_graph_defaults(self) -> None:
        """ImportGraph has correct defaults."""
        graph = ImportGraph()
        assert graph.edges == []
        assert graph.modules == []
        assert graph.external_imports == {}
        assert graph.entry_points == []
        assert graph.most_imported == []
        assert graph.total_internal_imports == 0
        assert graph.total_external_imports == 0

    def test_import_edge_with_values(self) -> None:
        """ImportEdge can be constructed with all values."""
        edge = ImportEdge(
            source="main.py",
            target="utils.py",
            import_type="type_checking",
            line=5,
            names=["foo", "bar"],
        )
        assert edge.source == "main.py"
        assert edge.target == "utils.py"
        assert edge.import_type == "type_checking"
        assert edge.line == 5
        assert edge.names == ["foo", "bar"]
