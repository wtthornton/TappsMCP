"""Tests for docs_mcp.validators.drift — drift detection."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from docs_mcp.validators.drift import (
    DriftDetector,
    DriftItem,
    DriftReport,
    _find_doc_files,
    _find_python_files,
    _iso_from_mtime,
)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestDriftItemModel:
    """Test DriftItem Pydantic model."""

    def test_defaults(self) -> None:
        item = DriftItem(file_path="src/app.py", drift_type="added_undocumented")
        assert item.severity == "warning"
        assert item.description == ""
        assert item.code_last_modified == ""
        assert item.doc_last_modified == ""

    def test_full_construction(self) -> None:
        item = DriftItem(
            file_path="src/app.py",
            drift_type="modified_undocumented",
            severity="error",
            description="Public names not found in docs: run",
            code_last_modified="2026-03-01T12:00:00",
            doc_last_modified="2026-02-01T12:00:00",
        )
        assert item.drift_type == "modified_undocumented"
        assert item.severity == "error"


class TestDriftReportModel:
    """Test DriftReport Pydantic model."""

    def test_defaults(self) -> None:
        report = DriftReport()
        assert report.total_items == 0
        assert report.items == []
        assert report.drift_score == 0.0
        assert report.checked_files == 0


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test helper functions."""

    def test_iso_from_mtime(self) -> None:
        # Use a known timestamp
        ts = 1709290800.0  # 2024-03-01 in some timezone
        result = _iso_from_mtime(ts)
        assert "T" in result
        assert len(result) == 20  # YYYY-MM-DDTHH:MM:SSZ
        assert result.endswith("Z")

    def test_find_python_files(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("x = 1", encoding="utf-8")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "mod.py").write_text("y = 2", encoding="utf-8")
        # Should skip __pycache__
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cached.py").write_text("z = 3", encoding="utf-8")

        files = _find_python_files(tmp_path)
        names = {f.name for f in files}
        assert "main.py" in names
        assert "mod.py" in names
        assert "cached.py" not in names

    def test_find_python_files_nonexistent(self) -> None:
        result = _find_python_files(Path("/nonexistent/path"))
        assert result == []

    def test_find_doc_files_default(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("# Guide", encoding="utf-8")

        files = _find_doc_files(tmp_path)
        names = {f.name for f in files}
        assert "README.md" in names
        assert "guide.md" in names

    def test_find_doc_files_specific_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "api.md").write_text("# API", encoding="utf-8")

        files = _find_doc_files(tmp_path, doc_dirs=["docs"])
        names = {f.name for f in files}
        assert "api.md" in names
        # Root-level README should NOT be included when dirs are specified
        assert "README.md" not in names


# ---------------------------------------------------------------------------
# DriftDetector tests
# ---------------------------------------------------------------------------


class TestDriftDetector:
    """Test DriftDetector.check()."""

    def test_empty_project(self, tmp_path: Path) -> None:
        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.total_items == 0
        assert report.checked_files == 0
        assert report.drift_score == 0.0

    def test_nonexistent_root(self) -> None:
        detector = DriftDetector()
        report = detector.check(Path("/nonexistent/path"))
        assert report.total_items == 0
        assert report.checked_files == 0

    def test_no_drift_when_docs_cover_api(self, tmp_path: Path) -> None:
        """When docs mention all public names, no drift should be detected."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            '"""App module."""\n\ndef run() -> None:\n    """Run the app."""\n    pass\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nThe `run` function starts the app.\n",
            encoding="utf-8",
        )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.total_items == 0

    def test_drift_detected_for_undocumented_api(self, tmp_path: Path) -> None:
        """When public names are not in docs, drift should be detected."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            '"""App module."""\n\n'
            "def calculate_total() -> float:\n"
            '    """Calculate total."""\n'
            "    return 0.0\n\n"
            "class PaymentProcessor:\n"
            '    """Process payments."""\n'
            "    pass\n",
            encoding="utf-8",
        )
        # README doesn't mention these names
        (tmp_path / "README.md").write_text(
            "# Project\n\nThis is a project.\n",
            encoding="utf-8",
        )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.total_items > 0
        assert report.drift_score > 0.0
        assert report.checked_files > 0

    def test_drift_with_no_docs(self, tmp_path: Path) -> None:
        """When there are no doc files, all public APIs are undocumented."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            '"""Module."""\n\ndef hello() -> str:\n    return "hi"\n',
            encoding="utf-8",
        )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.total_items > 0

    def test_empty_python_files_skipped(self, tmp_path: Path) -> None:
        """Empty Python files should not contribute to drift."""
        (tmp_path / "empty.py").write_text("", encoding="utf-8")
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.checked_files == 0

    def test_drift_score_capped_at_one(self, tmp_path: Path) -> None:
        """Drift score should never exceed 1.0."""
        # Create multiple source files with undocumented APIs
        src = tmp_path / "src"
        src.mkdir()
        for i in range(5):
            (src / f"mod{i}.py").write_text(
                f'"""Module {i}."""\n\ndef func_{i}() -> None:\n    pass\n',
                encoding="utf-8",
            )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.drift_score <= 1.0

    def test_severity_error_when_code_newer(self, tmp_path: Path) -> None:
        """When code is newer than docs, severity should be 'error'."""
        # Create doc file first
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n\nOld content.\n", encoding="utf-8")
        # Set doc mtime to past
        old_time = time.time() - 86400 * 30  # 30 days ago
        os.utime(readme, (old_time, old_time))

        # Create code file (will have current mtime)
        (tmp_path / "app.py").write_text(
            '"""Module."""\n\ndef new_feature() -> None:\n    pass\n',
            encoding="utf-8",
        )

        detector = DriftDetector()
        report = detector.check(tmp_path)
        assert report.items, "Expected drift items when code is newer than docs"
        # At least one item should have error severity
        severities = {item.severity for item in report.items}
        assert "error" in severities

    def test_doc_dirs_filter(self, tmp_path: Path) -> None:
        """doc_dirs parameter should restrict which docs are searched."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            '"""Module."""\n\ndef special_func() -> None:\n    pass\n',
            encoding="utf-8",
        )

        # Root README mentions the function
        (tmp_path / "README.md").write_text(
            "# Project\n\nUse special_func to do things.\n",
            encoding="utf-8",
        )

        # docs/ directory does NOT mention it
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text(
            "# Guide\n\nGeneral usage.\n",
            encoding="utf-8",
        )

        detector = DriftDetector()

        # When searching all docs, no drift (README mentions it)
        report_all = detector.check(tmp_path)
        drift_files_all = {item.file_path for item in report_all.items}

        # When restricting to docs/ only, drift detected
        report_docs = detector.check(tmp_path, doc_dirs=["docs"])
        assert report_docs.total_items > 0
