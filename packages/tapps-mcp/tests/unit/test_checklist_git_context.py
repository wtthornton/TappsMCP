"""Tests for checklist git context (Story 75.5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.tools.checklist import _get_git_context


class TestGetGitContext:
    @pytest.mark.asyncio
    async def test_returns_git_context(self) -> None:
        """Git context includes branch, sha, dirty status."""

        async def mock_run(cmd: list[str], **kwargs: object) -> AsyncMock:
            result = AsyncMock()
            result.returncode = 0
            if "rev-parse" in cmd and "--abbrev-ref" in cmd:
                result.stdout = "master\n"
            elif "rev-parse" in cmd and "--short" in cmd:
                result.stdout = "a80f38c7\n"
            elif "rev-parse" in cmd:
                result.stdout = "a80f38c7abcdef1234567890\n"
            elif "status" in cmd:
                result.stdout = ""
            return result

        with patch("tapps_mcp.tools.subprocess_runner.run_command_async", side_effect=mock_run):
            ctx = await _get_git_context()
            assert ctx is not None
            assert ctx["branch"] == "master"
            assert ctx["head_sha"] == "a80f38c7"
            assert ctx["head_sha_full"] == "a80f38c7abcdef1234567890"
            assert ctx["dirty"] is False

    @pytest.mark.asyncio
    async def test_returns_none_when_git_unavailable(self) -> None:
        """Returns None gracefully when not in a git repo."""

        async def mock_run(cmd: list[str], **kwargs: object) -> AsyncMock:
            result = AsyncMock()
            result.returncode = 128
            result.stdout = ""
            return result

        with patch("tapps_mcp.tools.subprocess_runner.run_command_async", side_effect=mock_run):
            ctx = await _get_git_context()
            assert ctx is None

    @pytest.mark.asyncio
    async def test_commit_sha_override(self) -> None:
        """Explicit commit_sha overrides auto-detected HEAD."""

        async def mock_run(cmd: list[str], **kwargs: object) -> AsyncMock:
            result = AsyncMock()
            result.returncode = 0
            if "--abbrev-ref" in cmd:
                result.stdout = "feature-branch\n"
            elif "--short" in cmd:
                result.stdout = "abc12345\n"
            elif "rev-parse" in cmd:
                result.stdout = "abc12345full\n"
            elif "status" in cmd:
                result.stdout = "M file.py\n"
            return result

        with patch("tapps_mcp.tools.subprocess_runner.run_command_async", side_effect=mock_run):
            ctx = await _get_git_context(commit_sha="deadbeef12345678")
            assert ctx is not None
            assert ctx["head_sha"] == "deadbeef"
            assert ctx["head_sha_full"] == "deadbeef12345678"
            assert ctx["branch"] == "feature-branch"
            assert ctx["dirty"] is True

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self) -> None:
        """Returns None on unexpected errors."""
        with patch(
            "tapps_mcp.tools.subprocess_runner.run_command_async",
            side_effect=RuntimeError("boom"),
        ):
            ctx = await _get_git_context()
            assert ctx is None

    @pytest.mark.asyncio
    async def test_dirty_when_porcelain_has_output(self) -> None:
        """Dirty is True when git status --porcelain has output."""

        async def mock_run(cmd: list[str], **kwargs: object) -> AsyncMock:
            result = AsyncMock()
            result.returncode = 0
            if "--abbrev-ref" in cmd:
                result.stdout = "main\n"
            elif "--short" in cmd:
                result.stdout = "1234abcd\n"
            elif "rev-parse" in cmd:
                result.stdout = "1234abcdfull\n"
            elif "status" in cmd:
                result.stdout = " M src/file.py\n?? new.py\n"
            return result

        with patch("tapps_mcp.tools.subprocess_runner.run_command_async", side_effect=mock_run):
            ctx = await _get_git_context()
            assert ctx is not None
            assert ctx["dirty"] is True

    @pytest.mark.asyncio
    async def test_empty_commit_sha_ignored(self) -> None:
        """Empty or whitespace commit_sha does not override."""

        async def mock_run(cmd: list[str], **kwargs: object) -> AsyncMock:
            result = AsyncMock()
            result.returncode = 0
            if "--abbrev-ref" in cmd:
                result.stdout = "main\n"
            elif "--short" in cmd:
                result.stdout = "abcd1234\n"
            elif "rev-parse" in cmd:
                result.stdout = "abcd1234full\n"
            elif "status" in cmd:
                result.stdout = ""
            return result

        with patch("tapps_mcp.tools.subprocess_runner.run_command_async", side_effect=mock_run):
            ctx = await _get_git_context(commit_sha="   ")
            assert ctx is not None
            assert ctx["head_sha"] == "abcd1234"
