"""Tests for cross-repo project path helpers (EPIC-112)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.tools.project_paths import (
    infer_monorepo_graph_root,
    resolve_effective_project_root,
    resolve_path_under_root,
    validate_read_path_under_root,
)


class TestResolveEffectiveProjectRoot:
    def test_default_when_override_empty(self, tmp_path: Path) -> None:
        result = resolve_effective_project_root(tmp_path, "")
        assert result.error_code is None
        assert result.root == tmp_path.resolve()

    def test_valid_override(self, tmp_path: Path) -> None:
        sibling = tmp_path / "other"
        sibling.mkdir()
        result = resolve_effective_project_root(tmp_path, str(sibling))
        assert result.error_code is None
        assert result.root == sibling.resolve()

    def test_invalid_override(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing"
        result = resolve_effective_project_root(tmp_path, str(missing))
        assert result.error_code == "invalid_project_root"
        assert "not an existing directory" in (result.error_message or "")


class TestResolvePathUnderRoot:
    def test_relative_under_root(self, tmp_path: Path) -> None:
        pkg = tmp_path / "packages" / "foo" / "src"
        pkg.mkdir(parents=True)
        resolved = resolve_path_under_root("packages/foo/src", tmp_path)
        assert resolved == pkg.resolve()

    def test_absolute_under_root(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "main.py"
        target.parent.mkdir(parents=True)
        target.write_text("x = 1\n", encoding="utf-8")
        resolved = resolve_path_under_root(str(target), tmp_path)
        assert resolved == target.resolve()

    def test_escape_rejected(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / "outside"
        outside.mkdir(exist_ok=True)
        with pytest.raises(ValueError, match="escapes project root"):
            resolve_path_under_root(str(outside), tmp_path)


class TestValidateReadPathUnderRoot:
    def test_repo_relative_file(self, tmp_path: Path) -> None:
        f = tmp_path / "lib" / "mod.py"
        f.parent.mkdir(parents=True)
        f.write_text("pass\n", encoding="utf-8")
        assert validate_read_path_under_root("lib/mod.py", tmp_path) == f.resolve()


class TestInferMonorepoGraphRoot:
    def test_packages_src_layout(self, tmp_path: Path) -> None:
        scope = tmp_path / "packages" / "tapps-mcp" / "src" / "tapps_mcp"
        scope.mkdir(parents=True)
        (tmp_path / "packages" / "tapps-mcp" / "pyproject.toml").write_text(
            "[project]\nname='tapps-mcp'\n",
            encoding="utf-8",
        )
        inferred = infer_monorepo_graph_root(tmp_path, scope)
        assert inferred == (tmp_path / "packages" / "tapps-mcp" / "src").resolve()

    def test_none_for_unrelated_scope(self, tmp_path: Path) -> None:
        scope = tmp_path / "docs"
        scope.mkdir()
        assert infer_monorepo_graph_root(tmp_path, scope) is None
