"""Tests for tapps_core.metrics.judge (TAP-478)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_core.metrics.judge import (
    JudgeDefinition,
    run_judge,
    run_judges,
)


class TestJudgeDefinition:
    def test_valid_exists_judge(self) -> None:
        jd = JudgeDefinition(type="exists", target="pyproject.toml")
        assert jd.type == "exists"
        assert jd.blocking is False

    def test_valid_grep_judge(self) -> None:
        jd = JudgeDefinition(type="grep", target="README.md", expect=r"\binstall\b")
        assert jd.expect == r"\binstall\b"

    def test_valid_pytest_judge(self) -> None:
        jd = JudgeDefinition(type="pytest", target="tests/unit/")
        assert jd.type == "pytest"


class TestExistsJudge:
    @pytest.mark.asyncio
    async def test_existing_file_passes(self, tmp_path: Path) -> None:
        (tmp_path / "target.txt").write_text("hello")
        jd = JudgeDefinition(type="exists", target=str(tmp_path / "target.txt"))
        result = await run_judge(jd)
        assert result.result == "pass"

    @pytest.mark.asyncio
    async def test_missing_file_fails(self, tmp_path: Path) -> None:
        jd = JudgeDefinition(type="exists", target=str(tmp_path / "missing.txt"))
        result = await run_judge(jd)
        assert result.result == "fail"


class TestGrepJudge:
    @pytest.mark.asyncio
    async def test_pattern_match_passes(self, tmp_path: Path) -> None:
        f = tmp_path / "code.py"
        f.write_text("def authenticate(user): pass\n")
        jd = JudgeDefinition(type="grep", target=str(f), expect="def authenticate")
        result = await run_judge(jd)
        assert result.result == "pass"

    @pytest.mark.asyncio
    async def test_no_match_fails(self, tmp_path: Path) -> None:
        f = tmp_path / "code.py"
        f.write_text("def foo(): pass\n")
        jd = JudgeDefinition(type="grep", target=str(f), expect="def authenticate")
        result = await run_judge(jd)
        assert result.result == "fail"

    @pytest.mark.asyncio
    async def test_missing_file_fails(self, tmp_path: Path) -> None:
        jd = JudgeDefinition(type="grep", target=str(tmp_path / "missing.py"), expect="foo")
        result = await run_judge(jd)
        assert result.result == "fail"


class TestPytestJudge:
    @pytest.mark.asyncio
    async def test_passing_tests_returns_pass(self, tmp_path: Path) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            jd = JudgeDefinition(type="pytest", target="tests/unit/")
            result = await run_judge(jd, cwd=tmp_path)
        assert result.result == "pass"

    @pytest.mark.asyncio
    async def test_failing_tests_returns_fail(self, tmp_path: Path) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"1 failed"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            jd = JudgeDefinition(type="pytest", target="tests/unit/")
            result = await run_judge(jd, cwd=tmp_path)
        assert result.result == "fail"

    @pytest.mark.asyncio
    async def test_pytest_not_found_returns_error(self, tmp_path: Path) -> None:
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            jd = JudgeDefinition(type="pytest", target="tests/")
            result = await run_judge(jd, cwd=tmp_path)
        assert result.result == "error"


class TestRunJudges:
    @pytest.mark.asyncio
    async def test_empty_list_passes(self) -> None:
        result = await run_judges([])
        assert result["judges_passed"] is True
        assert result["judge_results"] == []

    @pytest.mark.asyncio
    async def test_all_pass(self, tmp_path: Path) -> None:
        f = tmp_path / "exists.txt"
        f.touch()
        result = await run_judges([{"type": "exists", "target": str(f)}])
        assert result["judges_passed"] is True
        assert result["judge_results"][0]["result"] == "pass"

    @pytest.mark.asyncio
    async def test_non_blocking_fail_does_not_fail_overall(self, tmp_path: Path) -> None:
        result = await run_judges(
            [{"type": "exists", "target": str(tmp_path / "missing.txt"), "blocking": False}]
        )
        # Non-blocking failures should not set judges_passed=False
        assert result["judges_passed"] is True
        assert result["judge_results"][0]["result"] == "fail"

    @pytest.mark.asyncio
    async def test_blocking_fail_sets_judges_passed_false(self, tmp_path: Path) -> None:
        result = await run_judges(
            [{"type": "exists", "target": str(tmp_path / "missing.txt"), "blocking": True}]
        )
        assert result["judges_passed"] is False

    @pytest.mark.asyncio
    async def test_invalid_judge_returns_parse_error(self) -> None:
        result = await run_judges([{"type": "unknown_type", "target": "x"}])
        assert result["judges_passed"] is False
        assert "judge_parse_errors" in result

    @pytest.mark.asyncio
    async def test_mixed_judges(self, tmp_path: Path) -> None:
        f = tmp_path / "file.py"
        f.write_text("import os\n")
        result = await run_judges(
            [
                {"type": "exists", "target": str(f)},
                {"type": "grep", "target": str(f), "expect": "import os"},
            ]
        )
        assert result["judges_passed"] is True
        assert len(result["judge_results"]) == 2
