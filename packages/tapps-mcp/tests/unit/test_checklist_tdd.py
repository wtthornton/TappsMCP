"""Tests for tools.checklist_tdd — TDD stage validation (TAP-476).

Split out of ``test_checklist.py`` alongside the source split (TAP-5733).
These import through ``tapps_mcp.tools.checklist`` on purpose: that is the
backward-compatible path the re-export block promises, so these tests also
guard it.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class TestCheckTDDStages:
    """Tests for check_tdd_stages and helpers."""

    @pytest.mark.asyncio
    async def test_no_git_returns_skipped(self, tmp_path: Path) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from tapps_mcp.tools.checklist import check_tdd_stages

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch(
            "tapps_mcp.tools.subprocess_runner.run_command_async",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await check_tdd_stages(tmp_path)

        stages = {c.stage: c.result for c in result.checks}
        assert stages["red"] == "skipped"
        assert stages["green"] == "skipped"

    @pytest.mark.asyncio
    async def test_red_commit_found(self, tmp_path: Path) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from tapps_mcp.tools.checklist import check_tdd_stages

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "abc1234 test: add failing test for auth\ndef5678 fix: implement auth\n"
        )
        with patch(
            "tapps_mcp.tools.subprocess_runner.run_command_async",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await check_tdd_stages(tmp_path)

        stages = {c.stage: c.result for c in result.checks}
        assert stages["red"] == "passed"
        assert stages["green"] == "passed"

    @pytest.mark.asyncio
    async def test_missing_red_commit_fails(self, tmp_path: Path) -> None:
        from unittest.mock import AsyncMock, MagicMock, patch

        from tapps_mcp.tools.checklist import check_tdd_stages

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234 fix: implement auth\n"
        with patch(
            "tapps_mcp.tools.subprocess_runner.run_command_async",
            new=AsyncMock(return_value=mock_result),
        ):
            result = await check_tdd_stages(tmp_path)

        stages = {c.stage: c.result for c in result.checks}
        assert stages["red"] == "failed"
        assert result.passed is False

    def test_coverage_xml_parsed(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_coverage

        (tmp_path / "coverage.xml").write_text(
            '<?xml version="1.0" ?>\n<coverage line-rate="0.92" branch-rate="0.0"></coverage>\n'
        )
        check = _check_coverage(tmp_path)
        assert check.result == "passed"
        assert "92.0%" in check.message

    def test_coverage_below_threshold_fails(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_coverage

        (tmp_path / "coverage.xml").write_text(
            '<?xml version="1.0" ?>\n<coverage line-rate="0.55" branch-rate="0.0"></coverage>\n'
        )
        check = _check_coverage(tmp_path)
        assert check.result == "failed"

    def test_no_coverage_file_skipped(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_coverage

        check = _check_coverage(tmp_path)
        assert check.result == "skipped"

    def test_compile_time_red_flags_syntax_error(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_compile_time_red

        (tmp_path / "bad.py").write_text("def foo(\n  # unclosed\n")
        check = _check_compile_time_red(tmp_path)
        assert check.result == "failed"
        assert check.stage == "red_state"

    def test_valid_python_passes_compile_check(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.checklist import _check_compile_time_red

        (tmp_path / "good.py").write_text("def foo(): pass\n")
        check = _check_compile_time_red(tmp_path)
        assert check.result == "passed"
