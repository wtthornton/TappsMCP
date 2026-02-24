"""Tests for async tool detection (detect_installed_tools_async)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.tools.subprocess_utils import CommandResult
from tapps_mcp.tools.tool_detection import (
    _reset_tools_cache,
    detect_installed_tools,
    detect_installed_tools_async,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:  # type: ignore[misc]
    """Reset tool cache before each test."""
    _reset_tools_cache()
    yield  # type: ignore[misc]
    _reset_tools_cache()


class TestDetectInstalledToolsAsync:
    """Tests for the async parallel tool detection."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.tool_detection.shutil.which", return_value=None)
    async def test_no_tools_available(self, mock_which: object) -> None:
        """All tools missing returns unavailable entries."""
        results = await detect_installed_tools_async()
        assert len(results) == 6
        for tool in results:
            assert tool.available is False
            assert tool.version is None
            assert tool.install_hint is not None

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.tool_detection.run_command_async")
    @patch("tapps_mcp.tools.tool_detection.shutil.which", return_value="/usr/bin/ruff")
    async def test_all_tools_available(
        self, mock_which: object, mock_run: AsyncMock
    ) -> None:
        """All tools found returns version strings."""
        mock_run.return_value = CommandResult(
            returncode=0,
            stdout="tool 1.0.0",
            stderr="",
            command=["tool", "--version"],
        )
        results = await detect_installed_tools_async()
        assert len(results) == 6
        for tool in results:
            assert tool.available is True
            assert tool.version == "tool 1.0.0"
        # All 6 tools checked in parallel (6 calls total)
        assert mock_run.call_count == 6

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.tool_detection.shutil.which", return_value=None)
    async def test_cache_shared_with_sync(self, mock_which: object) -> None:
        """Async result is cached and sync function reads the same cache."""
        results_async = await detect_installed_tools_async()
        # Sync function should return cached results without calling shutil.which again
        mock_which.reset_mock()
        results_sync = detect_installed_tools()
        mock_which.assert_not_called()
        assert len(results_sync) == len(results_async)

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.tool_detection.shutil.which", return_value=None)
    async def test_sync_cache_used_by_async(self, mock_which: object) -> None:
        """Sync result cache is also used by async function."""
        results_sync = detect_installed_tools()
        mock_which.reset_mock()
        results_async = await detect_installed_tools_async()
        mock_which.assert_not_called()
        assert len(results_async) == len(results_sync)

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.tool_detection.run_command_async")
    @patch("tapps_mcp.tools.tool_detection.shutil.which")
    async def test_mixed_availability(
        self, mock_which: object, mock_run: AsyncMock
    ) -> None:
        """Some tools available, some missing."""

        def _which_side_effect(name: str) -> str | None:
            return "/usr/bin/ruff" if name == "ruff" else None

        mock_which.side_effect = _which_side_effect  # type: ignore[union-attr]
        mock_run.return_value = CommandResult(
            returncode=0,
            stdout="ruff 0.15.0",
            stderr="",
            command=["ruff", "--version"],
        )

        results = await detect_installed_tools_async()
        ruff = next(t for t in results if t.name == "ruff")
        mypy = next(t for t in results if t.name == "mypy")
        assert ruff.available is True
        assert ruff.version == "ruff 0.15.0"
        assert mypy.available is False
        assert mypy.install_hint is not None
        # Only ruff should trigger a subprocess call
        assert mock_run.call_count == 1

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.tool_detection.run_command_async")
    @patch("tapps_mcp.tools.tool_detection.shutil.which", return_value="/usr/bin/tool")
    async def test_version_command_failure(
        self, mock_which: object, mock_run: AsyncMock
    ) -> None:
        """Tool found but version command fails: available=True, version=None."""
        mock_run.return_value = CommandResult(
            returncode=1,
            stdout="",
            stderr="error",
            command=["tool", "--version"],
        )
        results = await detect_installed_tools_async()
        for tool in results:
            assert tool.available is True
            assert tool.version is None
