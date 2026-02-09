"""Unit tests for knowledge/library_detector.py."""

from __future__ import annotations

import json

from tapps_mcp.knowledge.library_detector import (
    _clean_package_name,
    _parse_package_json,
    _parse_pyproject,
    _parse_requirements,
    detect_libraries,
)


class TestCleanPackageName:
    def test_simple(self):
        assert _clean_package_name("fastapi") == "fastapi"

    def test_version_specifier(self):
        assert _clean_package_name("fastapi>=0.100") == "fastapi"

    def test_extras(self):
        assert _clean_package_name("mcp[cli]>=1.0") == "mcp"

    def test_underscore_to_dash(self):
        assert _clean_package_name("pydantic_settings") == "pydantic-settings"

    def test_comment(self):
        assert _clean_package_name("fastapi  # web framework") == "fastapi"

    def test_empty(self):
        assert _clean_package_name("") == ""

    def test_invalid(self):
        assert _clean_package_name("-e git+https://...") == ""


class TestParseRequirements:
    def test_basic(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("fastapi>=0.100\nuvicorn\npydantic>=2.0\n")
        result = _parse_requirements(req)
        assert "fastapi" in result
        assert "uvicorn" in result
        assert "pydantic" in result

    def test_comments_and_empty_lines(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("# comment\nfastapi\n\n# another\ndjango\n")
        result = _parse_requirements(req)
        assert "fastapi" in result
        assert "django" in result
        assert len(result) == 2

    def test_flags_skipped(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("-r base.txt\n-e .\nfastapi\n")
        result = _parse_requirements(req)
        assert result == ["fastapi"]

    def test_missing_file(self, tmp_path):
        result = _parse_requirements(tmp_path / "missing.txt")
        assert result == []


class TestParsePyproject:
    def test_basic(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\ndependencies = [\n    "fastapi>=0.100",\n    "pydantic>=2.0",\n]\n'
        )
        result = _parse_pyproject(pyproject)
        assert "fastapi" in result
        assert "pydantic" in result

    def test_inline_deps(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('dependencies = ["fastapi", "uvicorn"]\n')
        result = _parse_pyproject(pyproject)
        assert "fastapi" in result
        assert "uvicorn" in result

    def test_missing_file(self, tmp_path):
        result = _parse_pyproject(tmp_path / "missing.toml")
        assert result == []


class TestParsePackageJson:
    def test_basic(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(
            json.dumps(
                {
                    "dependencies": {"react": "^18.0", "next": "^13.0"},
                    "devDependencies": {"jest": "^29.0"},
                }
            )
        )
        result = _parse_package_json(pkg)
        assert "react" in result
        assert "next" in result
        assert "jest" in result

    def test_no_deps(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "my-app"}))
        result = _parse_package_json(pkg)
        assert result == []

    def test_invalid_json(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text("not json")
        result = _parse_package_json(pkg)
        assert result == []


class TestDetectLibraries:
    def test_from_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi\ndjango\n")
        result = detect_libraries(tmp_path)
        assert "django" in result
        assert "fastapi" in result

    def test_deduplication(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("fastapi\nfastapi\n")
        result = detect_libraries(tmp_path)
        assert result.count("fastapi") == 1

    def test_sorted(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("zebra\nalpha\nmiddle\n")
        result = detect_libraries(tmp_path)
        assert result == sorted(result)

    def test_empty_project(self, tmp_path):
        result = detect_libraries(tmp_path)
        assert result == []
