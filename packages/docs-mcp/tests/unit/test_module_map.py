"""Tests for the module structure analyzer."""

from __future__ import annotations

from pathlib import Path

from docs_mcp.analyzers.models import ModuleMap, ModuleNode
from docs_mcp.analyzers.module_map import ModuleMapAnalyzer


# ===================================================================
# Helpers
# ===================================================================


def _write(path: Path, content: str) -> None:
    """Write a file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_pkg(root: Path, name: str, init_content: str = "") -> Path:
    """Create a package directory with __init__.py."""
    pkg = root / name
    pkg.mkdir(parents=True, exist_ok=True)
    _write(pkg / "__init__.py", init_content)
    return pkg


def _find_node(nodes: list[ModuleNode], name: str) -> ModuleNode | None:
    """Find a node by name in a flat list."""
    for n in nodes:
        if n.name == name:
            return n
    return None


# ===================================================================
# Basic structure tests
# ===================================================================


class TestSingleFile:
    """Tests for projects with a single Python file."""

    def test_single_module(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "hello.py",
            '"""Hello module."""\n\ndef greet() -> None:\n    pass\n',
        )
        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert isinstance(result, ModuleMap)
        assert result.project_name == tmp_path.name
        assert result.total_modules == 1
        assert result.total_packages == 0
        assert len(result.module_tree) == 1
        node = result.module_tree[0]
        assert node.name == "hello"
        assert not node.is_package
        assert node.function_count == 1
        assert node.module_docstring == "Hello module."

    def test_empty_project(self, tmp_path: Path) -> None:
        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.total_modules == 0
        assert result.total_packages == 0
        assert result.module_tree == []
        assert result.entry_points == []


class TestPackageDetection:
    """Tests for package (directory with __init__.py) detection."""

    def test_single_package(self, tmp_path: Path) -> None:
        pkg = _make_pkg(tmp_path, "mylib", '"""My library."""\n')
        _write(pkg / "core.py", "def run() -> None:\n    pass\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.total_packages == 1
        assert result.total_modules == 1
        pkg_node = _find_node(result.module_tree, "mylib")
        assert pkg_node is not None
        assert pkg_node.is_package
        assert pkg_node.module_docstring == "My library."
        assert len(pkg_node.submodules) == 1
        assert pkg_node.submodules[0].name == "core"

    def test_nested_packages(self, tmp_path: Path) -> None:
        outer = _make_pkg(tmp_path, "outer")
        inner = _make_pkg(outer, "inner")
        _write(inner / "deep.py", "X = 1\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.total_packages == 2
        assert result.total_modules == 1
        outer_node = _find_node(result.module_tree, "outer")
        assert outer_node is not None
        inner_node = _find_node(outer_node.submodules, "inner")
        assert inner_node is not None
        assert inner_node.is_package
        deep_node = _find_node(inner_node.submodules, "deep")
        assert deep_node is not None
        assert not deep_node.is_package


# ===================================================================
# Depth limiting
# ===================================================================


class TestDepthLimiting:
    """Tests for max depth traversal."""

    def test_depth_zero_root_only(self, tmp_path: Path) -> None:
        pkg = _make_pkg(tmp_path, "pkg")
        _write(pkg / "mod.py", "X = 1\n")
        _write(tmp_path / "top.py", "Y = 2\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path, depth=0)

        # depth=0 means root only: top.py and the pkg itself
        assert result.total_modules == 1  # top.py
        assert result.total_packages == 1  # pkg
        pkg_node = _find_node(result.module_tree, "pkg")
        assert pkg_node is not None
        # Package node is built at depth 0, children at depth 1 which exceeds limit
        assert len(pkg_node.submodules) == 0

    def test_depth_one_allows_one_level(self, tmp_path: Path) -> None:
        pkg = _make_pkg(tmp_path, "pkg")
        sub = _make_pkg(pkg, "sub")
        _write(sub / "leaf.py", "Z = 3\n")
        _write(pkg / "mod.py", "X = 1\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path, depth=1)

        pkg_node = _find_node(result.module_tree, "pkg")
        assert pkg_node is not None
        # mod.py and sub/ are at depth 1 which is allowed
        mod_node = _find_node(pkg_node.submodules, "mod")
        assert mod_node is not None
        sub_node = _find_node(pkg_node.submodules, "sub")
        assert sub_node is not None
        # But leaf.py inside sub/ is at depth 2, which exceeds depth=1
        assert len(sub_node.submodules) == 0


# ===================================================================
# Private module filtering
# ===================================================================


class TestPrivateFiltering:
    """Tests for include_private parameter."""

    def test_excludes_private_by_default(self, tmp_path: Path) -> None:
        _write(tmp_path / "public.py", "def api() -> None:\n    pass\n")
        _write(tmp_path / "_internal.py", "def _helper() -> None:\n    pass\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path, include_private=False)

        assert result.total_modules == 1
        names = [n.name for n in result.module_tree]
        assert "public" in names
        assert "_internal" not in names

    def test_includes_private_when_requested(self, tmp_path: Path) -> None:
        _write(tmp_path / "public.py", "def api() -> None:\n    pass\n")
        _write(tmp_path / "_internal.py", "def _helper() -> None:\n    pass\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path, include_private=True)

        assert result.total_modules == 2
        names = [n.name for n in result.module_tree]
        assert "public" in names
        assert "_internal" in names

    def test_init_always_included(self, tmp_path: Path) -> None:
        """__init__.py should be processed for packages even with private filtering."""
        pkg = _make_pkg(tmp_path, "mypkg", '"""Package docstring."""\n')
        _write(pkg / "mod.py", "X = 1\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path, include_private=False)

        pkg_node = _find_node(result.module_tree, "mypkg")
        assert pkg_node is not None
        assert pkg_node.is_package
        assert pkg_node.module_docstring == "Package docstring."

    def test_private_directories_excluded(self, tmp_path: Path) -> None:
        _make_pkg(tmp_path, "_private_pkg")
        _write(tmp_path / "_private_pkg" / "mod.py", "X = 1\n")
        _make_pkg(tmp_path, "public_pkg")
        _write(tmp_path / "public_pkg" / "mod.py", "Y = 2\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path, include_private=False)

        names = [n.name for n in result.module_tree]
        assert "public_pkg" in names
        assert "_private_pkg" not in names


# ===================================================================
# Entry point detection
# ===================================================================


class TestEntryPoints:
    """Tests for __main__.py and if __name__ == '__main__' detection."""

    def test_main_block_detected(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "app.py",
            'def main() -> None:\n    pass\n\nif __name__ == "__main__":\n    main()\n',
        )

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert len(result.entry_points) == 1
        assert "app.py" in result.entry_points[0]
        node = _find_node(result.module_tree, "app")
        assert node is not None
        assert node.has_main

    def test_dunder_main_module(self, tmp_path: Path) -> None:
        pkg = _make_pkg(tmp_path, "cli")
        _write(pkg / "__main__.py", "print('hello')\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path, include_private=True)

        assert len(result.entry_points) >= 1
        main_paths = [ep for ep in result.entry_points if "__main__" in ep]
        assert len(main_paths) >= 1

    def test_no_entry_points(self, tmp_path: Path) -> None:
        _write(tmp_path / "utils.py", "def helper() -> int:\n    return 42\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.entry_points == []


# ===================================================================
# __all__ and public API counting
# ===================================================================


class TestPublicAPI:
    """Tests for __all__ extraction and public API counting."""

    def test_all_exports(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "exports.py",
            '__all__ = ["foo", "Bar"]\n\ndef foo() -> None:\n    pass\n\n'
            "def _secret() -> None:\n    pass\n\nclass Bar:\n    pass\n",
        )

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        node = _find_node(result.module_tree, "exports")
        assert node is not None
        assert node.all_exports == ["foo", "Bar"]
        assert node.public_api_count == 2

    def test_public_count_without_all(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "mixed.py",
            "def public_func() -> None:\n    pass\n\n"
            "def _private_func() -> None:\n    pass\n\n"
            "class PublicClass:\n    pass\n\n"
            "class _PrivateClass:\n    pass\n",
        )

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        node = _find_node(result.module_tree, "mixed")
        assert node is not None
        assert node.all_exports is None
        assert node.public_api_count == 2  # public_func + PublicClass
        assert node.function_count == 2
        assert node.class_count == 2


# ===================================================================
# Skip directory handling
# ===================================================================


class TestSkipDirs:
    """Tests for skipping common non-source directories."""

    def test_skips_pycache(self, tmp_path: Path) -> None:
        _write(tmp_path / "real.py", "X = 1\n")
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        _write(cache_dir / "real.cpython-312.pyc", "")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.total_modules == 1
        names = [n.name for n in result.module_tree]
        assert "real" in names

    def test_skips_dot_dirs(self, tmp_path: Path) -> None:
        _write(tmp_path / "app.py", "X = 1\n")
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        _write(git_dir / "config.py", "")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.total_modules == 1

    def test_skips_venv(self, tmp_path: Path) -> None:
        _write(tmp_path / "main.py", "X = 1\n")
        venv = tmp_path / "venv"
        venv.mkdir()
        _write(venv / "activate.py", "")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.total_modules == 1

    def test_skips_egg_info(self, tmp_path: Path) -> None:
        _write(tmp_path / "main.py", "X = 1\n")
        egg = tmp_path / "mylib.egg-info"
        egg.mkdir()
        _write(egg / "PKG-INFO", "")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.total_modules == 1


# ===================================================================
# Source directory detection
# ===================================================================


class TestSourceDirs:
    """Tests for auto-detection and explicit source directories."""

    def test_src_layout_auto_detected(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        pkg = _make_pkg(src, "mylib")
        _write(pkg / "core.py", "def run() -> None:\n    pass\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        # Auto-detection finds src/mylib/ as the source root and walks inside it.
        # Since mylib IS the source root, its contents (core.py) appear at the
        # top level of the tree.
        assert result.total_modules >= 1
        names = [n.name for n in result.module_tree]
        assert "core" in names

    def test_explicit_source_dirs(self, tmp_path: Path) -> None:
        lib = tmp_path / "lib"
        lib.mkdir()
        _write(lib / "util.py", "def helper() -> int:\n    return 1\n")
        _write(tmp_path / "ignored.py", "X = 1\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path, source_dirs=["lib"])

        names = [n.name for n in result.module_tree]
        assert "util" in names
        assert "ignored" not in names

    def test_explicit_source_dir_not_found_falls_back(self, tmp_path: Path) -> None:
        _write(tmp_path / "real.py", "X = 1\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path, source_dirs=["nonexistent"])

        # Falls back to project root
        assert result.total_modules == 1


# ===================================================================
# Module docstrings
# ===================================================================


class TestDocstrings:
    """Tests for module docstring extraction."""

    def test_docstring_extracted(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "documented.py",
            '"""This module does important work."""\n\nX = 1\n',
        )

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        node = _find_node(result.module_tree, "documented")
        assert node is not None
        assert node.module_docstring == "This module does important work."

    def test_no_docstring(self, tmp_path: Path) -> None:
        _write(tmp_path / "bare.py", "X = 1\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        node = _find_node(result.module_tree, "bare")
        assert node is not None
        assert node.module_docstring is None


# ===================================================================
# Aggregate statistics
# ===================================================================


class TestAggregateStats:
    """Tests for ModuleMap aggregate statistics."""

    def test_stats_correct(self, tmp_path: Path) -> None:
        pkg = _make_pkg(tmp_path, "app")
        _write(pkg / "models.py", "class User:\n    pass\n\nclass Post:\n    pass\n")
        _write(
            pkg / "views.py",
            "def index() -> None:\n    pass\n\ndef detail() -> None:\n    pass\n",
        )
        _write(tmp_path / "standalone.py", "def main() -> None:\n    pass\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.total_modules == 3  # models, views, standalone
        assert result.total_packages == 1  # app
        assert result.public_api_count >= 5  # User, Post, index, detail, main

    def test_public_api_uses_all_when_defined(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "limited.py",
            '__all__ = ["one"]\n\ndef one() -> None:\n    pass\n\n'
            "def two() -> None:\n    pass\n\ndef three() -> None:\n    pass\n",
        )

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        assert result.public_api_count == 1  # Only 'one' via __all__


# ===================================================================
# File size tracking
# ===================================================================


class TestFileSize:
    """Tests for size_bytes tracking."""

    def test_size_recorded(self, tmp_path: Path) -> None:
        content = "X = 1\n"
        file_path = tmp_path / "small.py"
        _write(file_path, content)

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        node = _find_node(result.module_tree, "small")
        assert node is not None
        # Use actual file size (may differ from len(content) on Windows due to \r\n)
        assert node.size_bytes == file_path.stat().st_size
        assert node.size_bytes > 0


# ===================================================================
# Sorting
# ===================================================================


class TestSorting:
    """Tests that output nodes are sorted by name."""

    def test_modules_sorted(self, tmp_path: Path) -> None:
        _write(tmp_path / "zebra.py", "X = 1\n")
        _write(tmp_path / "alpha.py", "Y = 2\n")
        _write(tmp_path / "middle.py", "Z = 3\n")

        analyzer = ModuleMapAnalyzer()
        result = analyzer.analyze(tmp_path)

        names = [n.name for n in result.module_tree]
        assert names == sorted(names)


# ===================================================================
# Model tests
# ===================================================================


class TestModels:
    """Tests for Pydantic model defaults and serialization."""

    def test_module_node_defaults(self) -> None:
        node = ModuleNode(name="test", path="test.py")
        assert not node.is_package
        assert node.submodules == []
        assert node.public_api_count == 0
        assert node.module_docstring is None
        assert not node.has_main
        assert node.all_exports is None
        assert node.size_bytes == 0
        assert node.function_count == 0
        assert node.class_count == 0

    def test_module_map_defaults(self) -> None:
        mm = ModuleMap(project_root="/tmp", project_name="test")
        assert mm.module_tree == []
        assert mm.entry_points == []
        assert mm.total_modules == 0
        assert mm.total_packages == 0
        assert mm.public_api_count == 0

    def test_module_node_roundtrip(self) -> None:
        node = ModuleNode(
            name="example",
            path="src/example.py",
            function_count=3,
            class_count=1,
            public_api_count=4,
        )
        data = node.model_dump()
        restored = ModuleNode.model_validate(data)
        assert restored == node
