"""Tests for knowledge freshness tracking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tapps_core.experts.knowledge_freshness import (
    KnowledgeFileMetadata,
    KnowledgeFreshnessTracker,
)


class TestKnowledgeFreshnessTracker:
    def _make_tracker(self, tmp_path: Path) -> KnowledgeFreshnessTracker:
        return KnowledgeFreshnessTracker(tmp_path / "metadata.json")

    def _make_knowledge_dir(self, tmp_path: Path) -> Path:
        kd = tmp_path / "knowledge"
        kd.mkdir()
        (kd / "security.md").write_text("# Security\n\nContent.", encoding="utf-8")
        (kd / "testing.md").write_text("# Testing\n\nContent.", encoding="utf-8")
        return kd

    def test_update_and_get_metadata(self, tmp_path: Path):
        tracker = self._make_tracker(tmp_path)
        fp = Path("security.md")
        tracker.update_file_metadata(fp, version="1.0", author="Alice")
        meta = tracker.get_file_metadata(fp)
        assert meta is not None
        assert meta.version == "1.0"
        assert meta.author == "Alice"
        assert meta.last_updated  # ISO timestamp

    def test_mark_deprecated(self, tmp_path: Path):
        tracker = self._make_tracker(tmp_path)
        fp = Path("old.md")
        tracker.mark_deprecated(fp, replacement_file="new.md")
        meta = tracker.get_file_metadata(fp)
        assert meta is not None
        assert meta.deprecated is True
        assert meta.replacement_file == "new.md"

    def test_get_stale_files(self, tmp_path: Path):
        tracker = self._make_tracker(tmp_path)
        kd = self._make_knowledge_dir(tmp_path)
        # Manually set an old timestamp.
        old_time = (datetime.now(tz=UTC) - timedelta(days=400)).isoformat()
        tracker._metadata[str(kd / "security.md")] = KnowledgeFileMetadata(
            file_path=str(kd / "security.md"),
            last_updated=old_time,
        )
        stale = tracker.get_stale_files(kd, max_age_days=365)
        assert len(stale) >= 1
        assert any("security" in str(p) for p, _ in stale)

    def test_get_stale_files_empty_dir(self, tmp_path: Path):
        tracker = self._make_tracker(tmp_path)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        stale = tracker.get_stale_files(empty_dir)
        assert stale == []

    def test_scan_and_update(self, tmp_path: Path):
        tracker = self._make_tracker(tmp_path)
        kd = self._make_knowledge_dir(tmp_path)
        result = tracker.scan_and_update(kd)
        assert result["scanned"] == 2
        assert result["new"] == 2

    def test_get_summary(self, tmp_path: Path):
        tracker = self._make_tracker(tmp_path)
        kd = self._make_knowledge_dir(tmp_path)
        tracker.scan_and_update(kd)
        summary = tracker.get_summary(kd)
        assert summary["total_files"] == 2
        assert "coverage" in summary

    def test_atomic_persistence(self, tmp_path: Path):
        tracker = self._make_tracker(tmp_path)
        fp = Path("test.md")
        tracker.update_file_metadata(fp, version="1.0")

        # Reload from disk.
        tracker2 = KnowledgeFreshnessTracker(tmp_path / "metadata.json")
        meta = tracker2.get_file_metadata(fp)
        assert meta is not None
        assert meta.version == "1.0"
