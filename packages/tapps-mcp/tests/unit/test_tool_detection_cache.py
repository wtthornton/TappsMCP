"""Tests for disk-based tool version caching (Story 52.1)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_core.common.models import InstalledTool
from tapps_mcp.tools.tool_detection import (
    _DISK_CACHE_MAX_AGE_SECONDS,
    _install_hint,
    _is_uv_tool_env,
    _read_disk_cache,
    _reset_tools_cache,
    _write_disk_cache,
    detect_installed_tools,
    detect_installed_tools_async,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:  # type: ignore[misc]
    """Reset tool cache before each test."""
    _reset_tools_cache()
    yield  # type: ignore[misc]
    _reset_tools_cache()


def _make_tools() -> list[InstalledTool]:
    """Create a sample list of InstalledTool objects."""
    return [
        InstalledTool(name="ruff", version="ruff 0.15.0", available=True, install_hint=None),
        InstalledTool(name="mypy", version=None, available=False, install_hint="pip install mypy"),
    ]


class TestDiskCacheWriteAndRead:
    """Test that detection results can be written to and read from disk cache."""

    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        """Detect tools, verify cache file written, read back correctly."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"
        tools = _make_tools()

        with patch(
            "tapps_mcp.tools.tool_detection._get_disk_cache_path",
            return_value=cache_file,
        ):
            _write_disk_cache(tools)
            assert cache_file.exists()

            # Verify JSON structure
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            assert "timestamp" in data
            assert "timestamp_epoch" in data
            assert "platform" in data
            assert "tools" in data
            assert len(data["tools"]) == 2
            assert data["tools"][0]["name"] == "ruff"
            assert data["tools"][0]["available"] is True

            # Read back
            result = _read_disk_cache()
            assert result is not None
            assert len(result) == 2
            assert result[0].name == "ruff"
            assert result[0].version == "ruff 0.15.0"
            assert result[1].name == "mypy"
            assert result[1].available is False

    def test_detect_writes_disk_cache(self, tmp_path: Path) -> None:
        """detect_installed_tools() writes results to disk."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"

        with (
            patch(
                "tapps_mcp.tools.tool_detection._get_disk_cache_path",
                return_value=cache_file,
            ),
            patch(
                "tapps_mcp.tools.tool_detection.shutil.which",
                return_value=None,
            ),
        ):
            detect_installed_tools()
            assert cache_file.exists()
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            assert len(data["tools"]) == 7

    @pytest.mark.asyncio
    async def test_async_detect_writes_disk_cache(self, tmp_path: Path) -> None:
        """detect_installed_tools_async() writes results to disk."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"

        with (
            patch(
                "tapps_mcp.tools.tool_detection._get_disk_cache_path",
                return_value=cache_file,
            ),
            patch(
                "tapps_mcp.tools.tool_detection.shutil.which",
                return_value=None,
            ),
        ):
            await detect_installed_tools_async()
            assert cache_file.exists()
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            assert len(data["tools"]) == 7


class TestDiskCacheExpiry:
    """Test that expired cache files trigger re-detection."""

    def test_expired_cache_returns_none(self, tmp_path: Path) -> None:
        """Write cache with old timestamp, verify re-detection occurs."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Write cache with timestamp > 24h ago
        old_data = {
            "timestamp": "2020-01-01T00:00:00Z",
            "timestamp_epoch": time.time() - _DISK_CACHE_MAX_AGE_SECONDS - 3600,
            "platform": __import__("sys").platform,
            "tools": [t.model_dump() for t in _make_tools()],
        }
        cache_file.write_text(json.dumps(old_data), encoding="utf-8")

        with patch(
            "tapps_mcp.tools.tool_detection._get_disk_cache_path",
            return_value=cache_file,
        ):
            result = _read_disk_cache()
            assert result is None

    def test_fresh_cache_returns_tools(self, tmp_path: Path) -> None:
        """Write cache with recent timestamp, verify it is returned."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        fresh_data = {
            "timestamp": "2026-03-05T00:00:00Z",
            "timestamp_epoch": time.time() - 60,  # 1 minute ago
            "platform": __import__("sys").platform,
            "tools": [t.model_dump() for t in _make_tools()],
        }
        cache_file.write_text(json.dumps(fresh_data), encoding="utf-8")

        with patch(
            "tapps_mcp.tools.tool_detection._get_disk_cache_path",
            return_value=cache_file,
        ):
            result = _read_disk_cache()
            assert result is not None
            assert len(result) == 2


class TestDiskCacheCorrupt:
    """Test graceful handling of corrupt cache files."""

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        """Write invalid JSON, verify graceful fallback."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text("NOT VALID JSON {{{", encoding="utf-8")

        with patch(
            "tapps_mcp.tools.tool_detection._get_disk_cache_path",
            return_value=cache_file,
        ):
            result = _read_disk_cache()
            assert result is None

    def test_missing_tools_key_returns_none(self, tmp_path: Path) -> None:
        """Write JSON without tools key, verify fallback."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({"timestamp_epoch": time.time()}),
            encoding="utf-8",
        )

        with patch(
            "tapps_mcp.tools.tool_detection._get_disk_cache_path",
            return_value=cache_file,
        ):
            result = _read_disk_cache()
            assert result is None

    def test_missing_timestamp_returns_none(self, tmp_path: Path) -> None:
        """Write JSON without timestamp_epoch, verify fallback."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({"tools": []}),
            encoding="utf-8",
        )

        with patch(
            "tapps_mcp.tools.tool_detection._get_disk_cache_path",
            return_value=cache_file,
        ):
            result = _read_disk_cache()
            assert result is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        """Non-existent cache file returns None."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"

        with patch(
            "tapps_mcp.tools.tool_detection._get_disk_cache_path",
            return_value=cache_file,
        ):
            result = _read_disk_cache()
            assert result is None

    def test_platform_mismatch_returns_none(self, tmp_path: Path) -> None:
        """Cache from a different platform is rejected."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "timestamp": "2026-03-05T00:00:00Z",
            "timestamp_epoch": time.time() - 60,
            "platform": "fake_platform_xyz",
            "tools": [t.model_dump() for t in _make_tools()],
        }
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        with patch(
            "tapps_mcp.tools.tool_detection._get_disk_cache_path",
            return_value=cache_file,
        ):
            result = _read_disk_cache()
            assert result is None


class TestForceRefresh:
    """Test that force_refresh bypasses all caches."""

    def test_force_refresh_bypasses_memory_cache(self) -> None:
        """force_refresh=True ignores in-memory cache."""
        with patch(
            "tapps_mcp.tools.tool_detection.shutil.which",
            return_value=None,
        ) as mock_which, patch(
            "tapps_mcp.tools.tool_detection._read_disk_cache",
            return_value=None,
        ), patch(
            "tapps_mcp.tools.tool_detection._write_disk_cache",
        ):
            # First call populates memory cache
            detect_installed_tools()
            mock_which.reset_mock()

            # Normal call uses memory cache
            detect_installed_tools()
            mock_which.assert_not_called()

            # Force refresh bypasses memory cache
            detect_installed_tools(force_refresh=True)
            assert mock_which.call_count > 0

    def test_force_refresh_bypasses_disk_cache(self, tmp_path: Path) -> None:
        """force_refresh=True ignores disk cache."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        # Write a valid disk cache
        data = {
            "timestamp": "2026-03-05T00:00:00Z",
            "timestamp_epoch": time.time() - 60,
            "platform": __import__("sys").platform,
            "tools": [t.model_dump() for t in _make_tools()],
        }
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        with (
            patch(
                "tapps_mcp.tools.tool_detection._get_disk_cache_path",
                return_value=cache_file,
            ),
            patch(
                "tapps_mcp.tools.tool_detection._venv_bin_dirs",
                return_value=[],
            ),
            patch(
                "tapps_mcp.tools.tool_detection.shutil.which",
                return_value=None,
            ) as mock_which,
        ):
            # Force refresh should NOT use disk cache
            result = detect_installed_tools(force_refresh=True)
            assert mock_which.call_count > 0
            # Results should reflect fresh detection (all unavailable)
            assert all(not t.available for t in result)

    @pytest.mark.asyncio
    async def test_async_force_refresh_bypasses_cache(self) -> None:
        """Async force_refresh=True ignores both caches."""
        with patch(
            "tapps_mcp.tools.tool_detection.shutil.which",
            return_value=None,
        ) as mock_which, patch(
            "tapps_mcp.tools.tool_detection._read_disk_cache",
            return_value=None,
        ), patch(
            "tapps_mcp.tools.tool_detection._write_disk_cache",
        ):
            # First call populates
            await detect_installed_tools_async()
            mock_which.reset_mock()

            # Normal call uses cache
            await detect_installed_tools_async()
            mock_which.assert_not_called()

            # Force refresh bypasses
            await detect_installed_tools_async(force_refresh=True)
            assert mock_which.call_count > 0


class TestDiskCacheIntegration:
    """Integration tests for disk cache with detect functions."""

    def test_disk_cache_populates_memory_cache(self, tmp_path: Path) -> None:
        """Disk cache hit populates the in-memory cache too."""
        cache_file = tmp_path / ".tapps-mcp" / "tool-versions.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        tools = _make_tools()
        data = {
            "timestamp": "2026-03-05T00:00:00Z",
            "timestamp_epoch": time.time() - 60,
            "platform": __import__("sys").platform,
            "tools": [t.model_dump() for t in tools],
        }
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        with (
            patch(
                "tapps_mcp.tools.tool_detection._get_disk_cache_path",
                return_value=cache_file,
            ),
            patch(
                "tapps_mcp.tools.tool_detection.shutil.which",
            ) as mock_which,
        ):
            # First call reads from disk
            result1 = detect_installed_tools()
            assert len(result1) == 2
            mock_which.assert_not_called()  # No subprocess calls

            # Second call uses memory cache (disk not even read)
            result2 = detect_installed_tools()
            assert len(result2) == 2


# ---------------------------------------------------------------------------
# Context-aware install hints (Issue #80.1)
# ---------------------------------------------------------------------------


class TestInstallHints:
    """Tests for context-aware install hints."""

    def test_pip_hint_when_not_uv(self, tmp_path: Path) -> None:
        """Returns pip install hint when not in a uv tool environment."""
        # Clear the cached value so our mock takes effect
        if hasattr(_is_uv_tool_env, "_cached"):
            delattr(_is_uv_tool_env, "_cached")
        with patch("tapps_mcp.tools.tool_detection.Path") as mock_path:
            mock_path.return_value.__truediv__ = lambda self, x: tmp_path / x
            # uv-receipt.toml does not exist
            (tmp_path / "uv-receipt.toml").unlink(missing_ok=True)
            # Need to patch Path(sys.prefix) to return tmp_path
            mock_path.side_effect = lambda x: tmp_path if x == sys.prefix else Path(x)
            # Simplest: just clear and re-check
            if hasattr(_is_uv_tool_env, "_cached"):
                delattr(_is_uv_tool_env, "_cached")
            # Patch at the function level
            with patch(
                "tapps_mcp.tools.tool_detection._is_uv_tool_env", return_value=False,
            ):
                hint = _install_hint("bandit")
            assert hint == "pip install bandit"
        # Clean up
        if hasattr(_is_uv_tool_env, "_cached"):
            delattr(_is_uv_tool_env, "_cached")

    def test_uv_hint_when_in_uv_env(self) -> None:
        """Returns uv tool install hint when in a uv tool environment."""
        if hasattr(_is_uv_tool_env, "_cached"):
            delattr(_is_uv_tool_env, "_cached")
        with patch(
            "tapps_mcp.tools.tool_detection._is_uv_tool_env", return_value=True,
        ):
            hint = _install_hint("bandit")
        assert hint == "uv tool install tapps-mcp --with bandit"
        if hasattr(_is_uv_tool_env, "_cached"):
            delattr(_is_uv_tool_env, "_cached")

    def test_uv_hint_for_pip_audit(self) -> None:
        """Hyphenated tool names preserved in hint."""
        with patch(
            "tapps_mcp.tools.tool_detection._is_uv_tool_env", return_value=True,
        ):
            hint = _install_hint("pip-audit")
        assert hint == "uv tool install tapps-mcp --with pip-audit"
        if hasattr(_is_uv_tool_env, "_cached"):
            delattr(_is_uv_tool_env, "_cached")
