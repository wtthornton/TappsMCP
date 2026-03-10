"""Tests for cache directory bootstrap (Story 75.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.server import _bootstrap_cache_dir, _cache_info_dict


class TestBootstrapCacheDir:
    def test_creates_cache_dir(self, tmp_path: Path) -> None:
        cache_dir, fallback = _bootstrap_cache_dir(tmp_path)
        assert cache_dir.is_dir()
        assert fallback is False
        assert cache_dir == tmp_path / ".tapps-mcp-cache"

    def test_env_var_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        custom = tmp_path / "custom-cache"
        monkeypatch.setenv("TAPPS_CACHE_DIR", str(custom))
        cache_dir, fallback = _bootstrap_cache_dir(tmp_path)
        assert cache_dir == custom
        assert cache_dir.is_dir()
        assert fallback is False

    def test_idempotent(self, tmp_path: Path) -> None:
        cache_dir1, _ = _bootstrap_cache_dir(tmp_path)
        cache_dir2, _ = _bootstrap_cache_dir(tmp_path)
        assert cache_dir1 == cache_dir2
        assert cache_dir1.is_dir()


class TestCacheInfoDict:
    def test_existing_writable_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "cache"
        d.mkdir()
        info = _cache_info_dict(d, fallback_used=False)
        assert info["exists"] is True
        assert info["writable"] is True
        assert info["fallback_used"] is False
        assert info["dir"] == str(d)

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "nonexistent"
        info = _cache_info_dict(d, fallback_used=False)
        assert info["exists"] is False
        assert info["writable"] is False
