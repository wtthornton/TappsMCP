"""Unit tests for report_studio tapps_init installer."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.report_studio.installer import (
    check_report_studio,
    install_report_studio,
)


def _sample_pyproject() -> str:
    return """[project]
name = "demo"
version = "0.1.0"
requires-python = ">=3.12"
"""


def test_install_report_studio_merges_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(_sample_pyproject(), encoding="utf-8")

    result = install_report_studio(tmp_path, tag="v0.1.3")

    text = pyproject.read_text(encoding="utf-8")
    assert "nlt-report-studio" in text
    assert 'tag = "v0.1.3"' in text
    assert result["pyproject_merged"] is True
    assert "pyproject.toml" in result["files_written"]


def test_install_report_studio_idempotent(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(_sample_pyproject(), encoding="utf-8")
    install_report_studio(tmp_path)
    before = pyproject.read_text(encoding="utf-8")
    install_report_studio(tmp_path)
    after = pyproject.read_text(encoding="utf-8")
    assert before == after


def test_install_report_studio_dry_run(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(_sample_pyproject(), encoding="utf-8")

    result = install_report_studio(tmp_path, dry_run=True)

    assert "nlt-report-studio" not in pyproject.read_text(encoding="utf-8")
    assert result["files_written"] == ["pyproject.toml"]


def test_check_report_studio(tmp_path: Path) -> None:
    assert check_report_studio(tmp_path)["installed"] is False
    (tmp_path / "pyproject.toml").write_text(_sample_pyproject(), encoding="utf-8")
    assert check_report_studio(tmp_path)["installed"] is False
    install_report_studio(tmp_path)
    probe = check_report_studio(tmp_path)
    assert probe["installed"] is True
    assert probe["has_reports_dir"] is False
