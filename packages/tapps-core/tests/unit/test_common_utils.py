"""Tests for tapps_core.common.utils."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tapps_core.common.utils import ensure_dir, read_text_utf8, utc_now


class TestUtcNow:
    def test_returns_datetime(self) -> None:
        result = utc_now()
        assert isinstance(result, datetime)

    def test_is_timezone_aware(self) -> None:
        result = utc_now()
        assert result.tzinfo is not None
        assert result.tzinfo == UTC


class TestEnsureDir:
    def test_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c"
        assert not target.exists()
        result = ensure_dir(target)
        assert target.is_dir()
        assert result == target

    def test_existing_directory(self, tmp_path: Path) -> None:
        result = ensure_dir(tmp_path)
        assert result == tmp_path

    def test_returns_path(self, tmp_path: Path) -> None:
        target = tmp_path / "new"
        result = ensure_dir(target)
        assert isinstance(result, Path)


class TestReadTextUtf8:
    def test_reads_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        assert read_text_utf8(f) == "hello world"

    def test_reads_unicode(self, tmp_path: Path) -> None:
        f = tmp_path / "unicode.txt"
        f.write_text("cafe\u0301", encoding="utf-8")
        assert read_text_utf8(f) == "cafe\u0301"
