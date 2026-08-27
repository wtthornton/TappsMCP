"""Tests for checklist git context (Story 75.5, TAP-6388)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.server_checklist_tools import _gather_git_context
from tapps_mcp.tools.checklist import _get_git_context


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_temp_repo(repo_dir: Path, branch: str) -> str:
    """Create a hermetic temp git repo on a distinct branch; return its HEAD SHA."""
    repo_dir.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "-q", "-b", branch], repo_dir)
    _run_git(["config", "user.email", "test@example.com"], repo_dir)
    _run_git(["config", "user.name", "Test"], repo_dir)
    (repo_dir / "marker.txt").write_text("tap-6388\n")
    _run_git(["add", "marker.txt"], repo_dir)
    _run_git(["commit", "-q", "-m", "tap-6388 regression commit"], repo_dir)
    return _run_git(["rev-parse", "HEAD"], repo_dir)


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


class TestGatherGitContextProjectRootThreading:
    """TAP-6388 (VAL-15): git_context must reflect *project_root*, never the
    server process's own cwd. Regression test uses a real hermetic temp git
    repo — never the live tapps-mcp checkout's state."""

    @pytest.mark.asyncio
    async def test_reports_target_project_branch_and_sha_not_process_cwd(
        self, tmp_path: Path
    ) -> None:
        target_repo = tmp_path / "target-project"
        branch_name = "tap-6388-regression-branch"
        target_sha = _init_temp_repo(target_repo, branch_name)

        live_repo_root = Path(
            _run_git(["rev-parse", "--show-toplevel"], Path(__file__).parent)
        )
        live_branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], live_repo_root)
        live_sha = _run_git(["rev-parse", "HEAD"], live_repo_root)

        ctx = await _gather_git_context(commit_sha="", project_root=target_repo)

        assert ctx is not None
        assert ctx["branch"] == branch_name
        assert ctx["head_sha_full"] == target_sha
        assert ctx["dirty"] is False

        # Negative control: must NOT be the live repo's own state, proving
        # the server process's actual cwd was not what got reported.
        assert ctx["branch"] != live_branch
        assert ctx["head_sha_full"] != live_sha

    @pytest.mark.asyncio
    async def test_not_a_git_repo_returns_none_not_silent_fallback(
        self, tmp_path: Path
    ) -> None:
        non_repo_dir = tmp_path / "not-a-repo"
        non_repo_dir.mkdir()

        ctx = await _gather_git_context(commit_sha="", project_root=non_repo_dir)

        assert ctx is None
