"""Tests for test-root discovery in the coverage heuristic (TAP-5619).

The heuristic used to look only under the scored file's own project root. In a
uv workspace the repo root has no `tests/` — they live inside the members — so
every top-level file scored zero coverage no matter how well tested it was.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.scoring.scorer import (
    _count_test_files,
    _test_roots,
    _workspace_members,
)


@pytest.fixture(autouse=True)
def _clear_test_root_cache() -> None:
    """`_test_roots` is lru_cached on the root path; tmp_path reuse would stick."""
    _test_roots.cache_clear()


def _single_package(root: Path) -> None:
    (root / "pyproject.toml").write_text('[project]\nname = "solo"\n')
    (root / "tests" / "unit").mkdir(parents=True)
    (root / "src").mkdir()


def _workspace(root: Path) -> None:
    (root / "pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["packages/*"]\n')
    for member in ("alpha", "beta"):
        (root / "packages" / member / "tests" / "unit").mkdir(parents=True)
    (root / "scripts").mkdir()


class TestWorkspaceMembers:
    def test_single_package_has_no_members(self, tmp_path: Path) -> None:
        _single_package(tmp_path)
        assert _workspace_members(tmp_path) == ()

    def test_member_globs_are_expanded(self, tmp_path: Path) -> None:
        _workspace(tmp_path)
        assert [p.name for p in _workspace_members(tmp_path)] == ["alpha", "beta"]

    def test_missing_pyproject_is_not_an_error(self, tmp_path: Path) -> None:
        assert _workspace_members(tmp_path) == ()

    def test_malformed_pyproject_is_not_an_error(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("this is not = valid toml [[[")
        assert _workspace_members(tmp_path) == ()

    def test_escaping_globs_are_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.uv.workspace]\nmembers = ["../elsewhere/*", "/etc"]\n'
        )
        assert _workspace_members(tmp_path) == ()


class TestTestRoots:
    def test_single_package_roots_are_project_local(self, tmp_path: Path) -> None:
        _single_package(tmp_path)
        assert set(_test_roots(tmp_path)) == {tmp_path / "tests", tmp_path / "tests" / "unit"}

    def test_workspace_roots_include_member_test_dirs(self, tmp_path: Path) -> None:
        _workspace(tmp_path)
        found = {p.relative_to(tmp_path).as_posix() for p in _test_roots(tmp_path)}
        assert found == {
            "packages/alpha/tests",
            "packages/alpha/tests/unit",
            "packages/beta/tests",
            "packages/beta/tests/unit",
        }

    def test_absent_directories_are_not_reported(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "empty"\n')
        assert _test_roots(tmp_path) == ()


class TestCountTestFiles:
    def test_member_test_file_counts_for_a_top_level_module(self, tmp_path: Path) -> None:
        """The TAP-5619 case: a scripts/ module tested from inside a member."""
        _workspace(tmp_path)
        (tmp_path / "packages" / "alpha" / "tests" / "unit" / "test_widget.py").touch()

        exact, fuzzy = _count_test_files(tmp_path, "widget")
        assert exact == 1
        assert fuzzy == 0

    def test_suffix_naming_also_counts(self, tmp_path: Path) -> None:
        _workspace(tmp_path)
        (tmp_path / "packages" / "beta" / "tests" / "widget_test.py").touch()

        exact, _fuzzy = _count_test_files(tmp_path, "widget")
        assert exact == 1

    def test_fuzzy_match_is_reported_separately(self, tmp_path: Path) -> None:
        _workspace(tmp_path)
        (tmp_path / "packages" / "alpha" / "tests" / "unit" / "test_widget_edges.py").touch()

        exact, fuzzy = _count_test_files(tmp_path, "widget")
        assert exact == 0
        assert fuzzy == 1

    def test_unrelated_test_file_does_not_count(self, tmp_path: Path) -> None:
        _workspace(tmp_path)
        (tmp_path / "packages" / "alpha" / "tests" / "unit" / "test_gadget.py").touch()

        assert _count_test_files(tmp_path, "widget") == (0, 0)

    def test_single_package_behaviour_is_unchanged(self, tmp_path: Path) -> None:
        _single_package(tmp_path)
        (tmp_path / "tests" / "unit" / "test_widget.py").touch()

        exact, _fuzzy = _count_test_files(tmp_path, "widget")
        assert exact == 1
