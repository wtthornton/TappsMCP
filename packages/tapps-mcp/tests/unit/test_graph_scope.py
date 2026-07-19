"""Graph walk scope: nested git checkouts and graph_exclude_patterns.

A sibling repo vendored inside the project root (e.g. ``projects/tapps-brain``
in a consuming project) must not leak into the call graph, import graph, or
fingerprints; consumers can also exclude arbitrary directories via the
``graph_exclude_patterns`` setting in ``.tapps-mcp.yaml``.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_fingerprint import (
    compute_index_fingerprint,
    fingerprint_settings,
)
from tapps_mcp.project.call_graph_types import INDEX_VERSION
from tapps_mcp.project.import_graph import _in_nested_repo, build_import_graph


def _write_project(root: Path) -> None:
    pkg = root / "myapp"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "main.py").write_text("def create_app():\n    return 1\n")


def _write_sibling_checkout(root: Path, *, git_as_file: bool = False) -> Path:
    """A nested repo under ``projects/`` — its own .git dir (or file)."""
    sibling = root / "projects" / "sibling-repo"
    src = sibling / "src" / "sibling"
    src.mkdir(parents=True)
    if git_as_file:
        (sibling / ".git").write_text("gitdir: /elsewhere\n")
    else:
        (sibling / ".git").mkdir()
    (src / "__init__.py").write_text("")
    (src / "http_adapter.py").write_text("def create_app():\n    return 2\n")
    return sibling


class TestInNestedRepo:
    def test_git_dir_marks_subtree(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        sibling = _write_sibling_checkout(tmp_path)
        inner = sibling / "src" / "sibling" / "http_adapter.py"
        assert _in_nested_repo(inner, tmp_path) is True
        assert _in_nested_repo(tmp_path / "myapp" / "main.py", tmp_path) is False

    def test_git_file_marks_subtree(self, tmp_path: Path) -> None:
        """Worktrees / submodules use a .git *file*, not a directory."""
        sibling = _write_sibling_checkout(tmp_path, git_as_file=True)
        inner = sibling / "src" / "sibling" / "http_adapter.py"
        assert _in_nested_repo(inner, tmp_path) is True

    def test_project_root_own_git_does_not_exclude(self, tmp_path: Path) -> None:
        """The project root's own .git must not mark everything nested."""
        (tmp_path / ".git").mkdir()
        _write_project(tmp_path)
        assert _in_nested_repo(tmp_path / "myapp" / "main.py", tmp_path) is False

    def test_cache_is_shared_across_files(self, tmp_path: Path) -> None:
        sibling = _write_sibling_checkout(tmp_path)
        cache: dict[Path, bool] = {}
        f1 = sibling / "src" / "sibling" / "http_adapter.py"
        f2 = sibling / "src" / "sibling" / "__init__.py"
        assert _in_nested_repo(f1, tmp_path, cache) is True
        assert _in_nested_repo(f2, tmp_path, cache) is True
        assert cache  # verdicts memoized per directory


class TestCallGraphScope:
    def test_nested_checkout_symbols_excluded(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        _write_sibling_checkout(tmp_path)
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        files = {s.file_path for s in index.symbols}
        assert any("myapp" in f for f in files)
        assert not any("sibling" in f for f in files)

    def test_graph_exclude_patterns_from_yaml(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        vendored = tmp_path / "vendored" / "lib"
        vendored.mkdir(parents=True)
        (vendored / "extra.py").write_text("def extra():\n    return 3\n")
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "graph_exclude_patterns:\n  - vendored\n"
        )
        index = build_call_graph_index(tmp_path, force_rebuild=True)
        files = {s.file_path for s in index.symbols}
        assert not any("vendored" in f for f in files)
        assert any("myapp" in f for f in files)


class TestImportGraphScope:
    def test_nested_checkout_modules_excluded(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        _write_sibling_checkout(tmp_path)
        graph = build_import_graph(tmp_path)
        assert any("myapp" in m for m in graph.modules)
        assert not any("sibling" in m for m in graph.modules)

    def test_impact_analyzer_graph_excludes_nested_checkout(self, tmp_path: Path) -> None:
        from tapps_mcp.project.impact_analyzer import build_import_graph as build_impact_graph

        _write_project(tmp_path)
        sibling = _write_sibling_checkout(tmp_path)
        (sibling / "src" / "sibling" / "consumer.py").write_text("import myapp.main\n")
        graph = build_impact_graph(tmp_path)
        dependents = graph.get("myapp.main", set())
        assert not any("sibling" in d for d in dependents)


class TestFingerprintScope:
    def test_exclude_patterns_change_fingerprint(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        without = fingerprint_settings(tmp_path)
        with_excludes = fingerprint_settings(tmp_path, exclude_patterns=["vendored"])
        fp_without = compute_index_fingerprint(without, index_version=INDEX_VERSION)
        fp_with = compute_index_fingerprint(with_excludes, index_version=INDEX_VERSION)
        assert fp_without != fp_with

    def test_yaml_graph_excludes_merged_into_settings(self, tmp_path: Path) -> None:
        _write_project(tmp_path)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "graph_exclude_patterns:\n  - vendored\n  - third_party\n"
        )
        settings = fingerprint_settings(tmp_path)
        assert "vendored" in settings.exclude_patterns
        assert "third_party" in settings.exclude_patterns
