"""Tests for the import analyzer module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from tapps_core.knowledge.import_analyzer import (
    _detect_project_package,
    extract_external_imports,
    find_uncached_libraries,
)


class TestExtractExternalImports:
    """Tests for extract_external_imports."""

    def test_filters_stdlib(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("import os\nimport sys\nfrom pathlib import Path\n")
        result = extract_external_imports(f, tmp_path)
        assert "os" not in result
        assert "sys" not in result
        assert "pathlib" not in result

    def test_finds_external_imports(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("import fastapi\nimport pydantic\nfrom httpx import Client\n")
        result = extract_external_imports(f, tmp_path)
        assert "fastapi" in result
        assert "pydantic" in result
        assert "httpx" in result

    def test_filters_project_local(self, tmp_path: Path) -> None:
        # Create src/myproject/ layout
        pkg_dir = tmp_path / "src" / "myproject"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "__init__.py").write_text("")

        f = tmp_path / "test.py"
        f.write_text("import myproject\nimport fastapi\n")
        result = extract_external_imports(f, tmp_path)
        assert "myproject" not in result
        assert "fastapi" in result

    def test_filters_private_modules(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("import _thread\nimport __future__\nimport fastapi\n")
        result = extract_external_imports(f, tmp_path)
        assert "_thread" not in result
        assert "__future__" not in result
        assert "fastapi" in result

    def test_filters_test_packages(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("import pytest\nimport mypy\nimport fastapi\n")
        result = extract_external_imports(f, tmp_path)
        assert "pytest" not in result
        assert "mypy" not in result
        assert "fastapi" in result

    def test_handles_from_import(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("from pydantic import BaseModel\nfrom mcp.server import FastMCP\n")
        result = extract_external_imports(f, tmp_path)
        assert "pydantic" in result
        assert "mcp" in result

    def test_returns_sorted(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("import zzz\nimport aaa\nimport mmm\n")
        result = extract_external_imports(f, tmp_path)
        assert result == sorted(result)

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("")
        result = extract_external_imports(f, tmp_path)
        assert result == []

    def test_syntax_error_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("def f(:\n  pass\n")
        result = extract_external_imports(f, tmp_path)
        assert result == []

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.py"
        result = extract_external_imports(f, tmp_path)
        assert result == []

    def test_deduplicates_imports(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("import fastapi\nfrom fastapi import Request\n")
        result = extract_external_imports(f, tmp_path)
        assert result.count("fastapi") == 1


class TestFindUncachedLibraries:
    """Tests for find_uncached_libraries."""

    def test_all_cached(self) -> None:
        cache = MagicMock()
        cache.has.return_value = True
        result = find_uncached_libraries(["fastapi", "pydantic"], cache)
        assert result == []

    def test_none_cached(self) -> None:
        cache = MagicMock()
        cache.has.return_value = False
        result = find_uncached_libraries(["fastapi", "pydantic"], cache)
        assert result == ["fastapi", "pydantic"]

    def test_partial_cache(self) -> None:
        cache = MagicMock()
        cache.has.side_effect = lambda lib: lib == "fastapi"
        result = find_uncached_libraries(["fastapi", "pydantic", "httpx"], cache)
        assert result == ["pydantic", "httpx"]

    def test_empty_input(self) -> None:
        cache = MagicMock()
        result = find_uncached_libraries([], cache)
        assert result == []


class TestDetectProjectPackage:
    """Tests for _detect_project_package."""

    def test_src_layout(self, tmp_path: Path) -> None:
        pkg = tmp_path / "src" / "myapp"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text("")
        assert _detect_project_package(tmp_path) == "myapp"

    def test_flat_layout(self, tmp_path: Path) -> None:
        pkg = tmp_path / "myapp"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        assert _detect_project_package(tmp_path) == "myapp"

    def test_skips_venv(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "__init__.py").write_text("")
        assert _detect_project_package(tmp_path) is None

    def test_no_packages(self, tmp_path: Path) -> None:
        assert _detect_project_package(tmp_path) is None
