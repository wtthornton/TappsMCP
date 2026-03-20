"""Tests for docs_mcp.validators.freshness — freshness scoring."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from docs_mcp.validators.freshness import (
    FreshnessChecker,
    FreshnessItem,
    FreshnessReport,
    _classify_freshness,
    _freshness_weight,
)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestFreshnessItemModel:
    """Test FreshnessItem Pydantic model."""

    def test_construction(self) -> None:
        item = FreshnessItem(
            file_path="README.md",
            last_modified="2026-03-01T12:00:00",
            age_days=5,
            freshness="fresh",
        )
        assert item.file_path == "README.md"
        assert item.age_days == 5
        assert item.freshness == "fresh"


class TestFreshnessReportModel:
    """Test FreshnessReport Pydantic model."""

    def test_defaults(self) -> None:
        report = FreshnessReport()
        assert report.items == []
        assert report.average_age_days == 0.0
        assert report.freshness_score == 0.0


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestClassifyFreshness:
    """Test _classify_freshness helper."""

    @pytest.mark.parametrize(
        "age_days,expected",
        [
            (0, "fresh"),
            (15, "fresh"),
            (29, "fresh"),
            (30, "aging"),
            (60, "aging"),
            (89, "aging"),
            (90, "stale"),
            (200, "stale"),
            (364, "stale"),
            (365, "ancient"),
            (1000, "ancient"),
        ],
        ids=[
            "fresh-0d",
            "fresh-15d",
            "fresh-29d",
            "aging-30d",
            "aging-60d",
            "aging-89d",
            "stale-90d",
            "stale-200d",
            "stale-364d",
            "ancient-365d",
            "ancient-1000d",
        ],
    )
    def test_classify(self, age_days: int, expected: str) -> None:
        assert _classify_freshness(age_days) == expected


class TestFreshnessWeight:
    """Test _freshness_weight helper."""

    def test_fresh_file_high_weight(self) -> None:
        weight = _freshness_weight(0)
        assert weight == pytest.approx(1.0, abs=0.01)

    def test_90_day_file_half_weight(self) -> None:
        weight = _freshness_weight(90)
        assert weight == pytest.approx(0.5, abs=0.05)

    def test_old_file_low_weight(self) -> None:
        weight = _freshness_weight(365)
        assert weight < 0.1

    def test_weight_decreases_with_age(self) -> None:
        w0 = _freshness_weight(0)
        w30 = _freshness_weight(30)
        w90 = _freshness_weight(90)
        w365 = _freshness_weight(365)
        assert w0 > w30 > w90 > w365


# ---------------------------------------------------------------------------
# FreshnessChecker tests
# ---------------------------------------------------------------------------


class TestFreshnessChecker:
    """Test FreshnessChecker.check()."""

    def test_nonexistent_root(self) -> None:
        checker = FreshnessChecker()
        report = checker.check(Path("/nonexistent/path"))
        assert report.items == []
        assert report.freshness_score == 0.0

    def test_empty_project(self, tmp_path: Path) -> None:
        checker = FreshnessChecker()
        report = checker.check(tmp_path)
        assert report.items == []
        assert report.freshness_score == 0.0

    def test_fresh_files_high_score(self, tmp_path: Path) -> None:
        """Recently created files should result in a high score."""
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        assert len(report.items) == 2
        assert report.freshness_score > 90.0
        for item in report.items:
            assert item.freshness == "fresh"

    def test_stale_files_lower_score(self, tmp_path: Path) -> None:
        """Files modified long ago should result in a lower score."""
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n", encoding="utf-8")
        # Set mtime to 200 days ago
        old_time = time.time() - 86400 * 200
        os.utime(readme, (old_time, old_time))

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        assert len(report.items) == 1
        assert report.items[0].freshness == "stale"
        assert report.freshness_score < 50.0

    def test_ancient_files(self, tmp_path: Path) -> None:
        """Files older than 365 days should be classified as ancient."""
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n", encoding="utf-8")
        # Set mtime to 2 years ago
        old_time = time.time() - 86400 * 730
        os.utime(readme, (old_time, old_time))

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        assert report.items[0].freshness == "ancient"
        assert report.items[0].age_days >= 365

    def test_mixed_freshness(self, tmp_path: Path) -> None:
        """Mix of fresh and old files should give intermediate score."""
        # Fresh file
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        # Old file
        old_doc = tmp_path / "old.md"
        old_doc.write_text("# Old\n", encoding="utf-8")
        old_time = time.time() - 86400 * 200
        os.utime(old_doc, (old_time, old_time))

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        assert len(report.items) == 2
        freshness_labels = {item.freshness for item in report.items}
        assert "fresh" in freshness_labels

    def test_average_age_calculation(self, tmp_path: Path) -> None:
        """Average age should be calculated correctly."""
        (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        # Both files just created, average age should be very low
        assert report.average_age_days < 1.0

    def test_score_between_0_and_100(self, tmp_path: Path) -> None:
        """Score should always be within valid range."""
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        assert 0.0 <= report.freshness_score <= 100.0

    def test_skip_dirs_honored(self, tmp_path: Path) -> None:
        """Documentation files inside skipped directories should be ignored."""
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "hidden.md").write_text("# Hidden\n", encoding="utf-8")

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        file_paths = {item.file_path for item in report.items}
        assert "README.md" in file_paths
        assert not any(".venv" in fp for fp in file_paths)

    def test_iso_date_format(self, tmp_path: Path) -> None:
        """last_modified should be in ISO format."""
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        assert len(report.items) == 1
        iso = report.items[0].last_modified
        assert "T" in iso
        assert len(iso) == 20  # YYYY-MM-DDTHH:MM:SSZ
        assert iso.endswith("Z")

    # -------------------------------------------------------------------
    # Epic 88: Sort, category counts, relative_to
    # -------------------------------------------------------------------

    def test_category_counts(self, tmp_path: Path) -> None:
        """category_counts should tally each freshness category."""
        (tmp_path / "new.md").write_text("n\n", encoding="utf-8")

        old = tmp_path / "old.md"
        old.write_text("o\n", encoding="utf-8")
        old_time = time.time() - 86400 * 200
        os.utime(old, (old_time, old_time))

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        assert report.category_counts["fresh"] == 1
        assert report.category_counts["stale"] == 1
        assert report.category_counts["aging"] == 0
        assert report.category_counts["ancient"] == 0

    def test_items_sorted_stalest_first(self, tmp_path: Path) -> None:
        """Items should be sorted by age_days descending."""
        (tmp_path / "new.md").write_text("n\n", encoding="utf-8")

        old = tmp_path / "old.md"
        old.write_text("o\n", encoding="utf-8")
        old_time = time.time() - 86400 * 200
        os.utime(old, (old_time, old_time))

        checker = FreshnessChecker()
        report = checker.check(tmp_path)

        ages = [item.age_days for item in report.items]
        assert ages == sorted(ages, reverse=True)

    def test_relative_to_parameter(self, tmp_path: Path) -> None:
        """relative_to should control the base for file_path computation."""
        sub = tmp_path / "docs"
        sub.mkdir()
        (sub / "guide.md").write_text("g\n", encoding="utf-8")

        checker = FreshnessChecker()
        report = checker.check(sub, relative_to=tmp_path)

        assert len(report.items) == 1
        assert report.items[0].file_path == "docs/guide.md"

    def test_empty_report_has_category_counts(self) -> None:
        """Empty report should have zeroed category counts."""
        report = FreshnessReport()
        assert report.category_counts == {
            "fresh": 0, "aging": 0, "stale": 0, "ancient": 0,
        }
