"""Tests for composite tools (session_start, validate_changed, quick_check)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.checklist import CallTracker


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:  # type: ignore[misc]
    """Reset CallTracker before every test."""
    CallTracker.reset()


# ---------------------------------------------------------------------------
# tapps_session_start
# ---------------------------------------------------------------------------


class TestTappsSessionStart:
    """Tests for the tapps_session_start composite tool."""

    def test_returns_success(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = tapps_session_start()
        assert result["success"] is True
        assert result["tool"] == "tapps_session_start"

    def test_includes_server_and_profile_data(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = tapps_session_start()
        data = result["data"]
        assert "server" in data
        assert "configuration" in data
        assert "pipeline" in data
        assert "quick_start" in data
        assert "critical_rules" in data
        # project_profile may be present or None depending on env
        assert "project_profile" in data

    def test_records_all_calls(self) -> None:
        from tapps_mcp.server import tapps_session_start

        tapps_session_start()
        called = CallTracker.get_called_tools()
        assert "tapps_session_start" in called
        assert "tapps_server_info" in called
        assert "tapps_project_profile" in called

    def test_includes_next_steps(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = tapps_session_start()
        assert "next_steps" in result["data"]

    def test_includes_pipeline_progress(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = tapps_session_start()
        progress = result["data"]["pipeline_progress"]
        assert "discover" in progress["completed_stages"]


# ---------------------------------------------------------------------------
# tapps_validate_changed
# ---------------------------------------------------------------------------


class TestTappsValidateChanged:
    """Tests for the tapps_validate_changed batch tool."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_no_files_returns_empty(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        from tapps_mcp.server import tapps_validate_changed

        mock_settings.return_value.project_root = Path("/fake")
        mock_settings.return_value.tool_timeout = 30

        with patch(
            "tapps_mcp.tools.batch_validator.detect_changed_python_files",
            return_value=[],
        ):
            result = await tapps_validate_changed()

        assert result["success"] is True
        assert result["data"]["files_validated"] == 0
        assert result["data"]["all_gates_passed"] is True

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_explicit_file_paths(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_validate_changed(file_paths=str(f))
        assert result["success"] is True
        assert result["data"]["files_validated"] == 1

    @pytest.mark.asyncio
    async def test_records_call(self) -> None:
        from tapps_mcp.server import tapps_validate_changed

        with (
            patch(
                "tapps_mcp.tools.batch_validator.detect_changed_python_files",
                return_value=[],
            ),
            patch("tapps_mcp.server.load_settings") as mock_settings,
        ):
            mock_settings.return_value.project_root = Path("/fake")
            await tapps_validate_changed()

        assert "tapps_validate_changed" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    async def test_parallel_execution_multiple_files(self, tmp_path: Path) -> None:
        """Multiple files are all validated (parallel gather)."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        files = []
        for name in ("a.py", "b.py", "c.py"):
            f = tmp_path / name
            f.write_text("x = 1\n", encoding="utf-8")
            files.append(f)

        mock_score = ScoreResult(
            file_path="test.py",
            categories={},
            overall_score=85.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file = AsyncMock(return_value=mock_score)

        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=lambda p: Path(p)),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            result = await tapps_validate_changed(
                file_paths=",".join(str(f) for f in files),
                include_security=False,
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 3
        assert mock_scorer.score_file.call_count == 3

    @pytest.mark.asyncio
    async def test_no_duplicate_security_scan(self, tmp_path: Path) -> None:
        """run_security_scan is NOT called; bandit results reused from score."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path=str(f),
            categories={},
            overall_score=85.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file = AsyncMock(return_value=mock_score)

        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", return_value=f),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.security.security_scanner.run_security_scan",
            ) as mock_run_sec,
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            result = await tapps_validate_changed(
                file_paths=str(f),
                include_security=True,
            )

        # run_security_scan should NOT be called — bandit reused from score
        mock_run_sec.assert_not_called()
        assert result["data"]["files_validated"] == 1
        data = result["data"]["results"][0]
        assert data["security_passed"] is True
        assert data["security_issues"] == 0

    @pytest.mark.asyncio
    async def test_secret_scanner_still_runs(self, tmp_path: Path) -> None:
        """SecretScanner.scan_file IS called when include_security=True."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.security.secret_scanner import SecretScanResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path=str(f),
            categories={},
            overall_score=85.0,
            security_issues=[],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file = AsyncMock(return_value=mock_score)

        mock_gate = MagicMock(passed=True, failures=[])
        mock_secret_result = SecretScanResult(
            total_findings=0, high_severity=0, scanned_files=1
        )
        mock_scanner_instance = MagicMock()
        mock_scanner_instance.scan_file.return_value = mock_secret_result

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", return_value=f),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.security.secret_scanner.SecretScanner",
                return_value=mock_scanner_instance,
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            await tapps_validate_changed(file_paths=str(f), include_security=True)

        mock_scanner_instance.scan_file.assert_called_once_with(str(f))

    @pytest.mark.asyncio
    async def test_individual_file_error_doesnt_abort_batch(
        self, tmp_path: Path
    ) -> None:
        """One file raising an exception doesn't prevent others from validating."""
        from tapps_mcp.scoring.models import ScoreResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        good = tmp_path / "good.py"
        good.write_text("x = 1\n", encoding="utf-8")
        bad = tmp_path / "bad.py"
        bad.write_text("y = 2\n", encoding="utf-8")

        mock_score = ScoreResult(
            file_path="test.py",
            categories={},
            overall_score=85.0,
            security_issues=[],
        )

        async def _score_side_effect(path: Path, **kwargs: object) -> ScoreResult:
            if "bad" in str(path):
                raise RuntimeError("score failed")
            return mock_score

        mock_scorer = MagicMock()
        mock_scorer.score_file = AsyncMock(side_effect=_score_side_effect)

        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=lambda p: Path(p)),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            result = await tapps_validate_changed(
                file_paths=f"{good},{bad}",
                include_security=False,
            )

        assert result["data"]["files_validated"] == 2
        results_list = result["data"]["results"]
        # One succeeded, one has errors
        errored = [r for r in results_list if "errors" in r]
        succeeded = [r for r in results_list if "overall_score" in r]
        assert len(errored) == 1
        assert len(succeeded) == 1
        assert "score failed" in errored[0]["errors"][0]

    @pytest.mark.asyncio
    async def test_security_combines_bandit_and_secrets(self, tmp_path: Path) -> None:
        """Security result aggregates bandit issues from score + secret findings."""
        from tapps_mcp.scoring.models import ScoreResult, SecurityIssue
        from tapps_mcp.security.secret_scanner import SecretScanResult
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        bandit_issue = SecurityIssue(
            code="B101",
            message="Use of assert",
            file=str(f),
            line=1,
            severity="low",
        )
        mock_score = ScoreResult(
            file_path=str(f),
            categories={},
            overall_score=85.0,
            security_issues=[bandit_issue],
        )
        mock_scorer = MagicMock()
        mock_scorer.score_file = AsyncMock(return_value=mock_score)

        mock_gate = MagicMock(passed=True, failures=[])
        mock_secret_result = SecretScanResult(
            total_findings=1, high_severity=1, scanned_files=1
        )
        mock_scanner_instance = MagicMock()
        mock_scanner_instance.scan_file.return_value = mock_secret_result

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", return_value=f),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=mock_scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.security.secret_scanner.SecretScanner",
                return_value=mock_scanner_instance,
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            result = await tapps_validate_changed(
                file_paths=str(f), include_security=True
            )

        file_result = result["data"]["results"][0]
        # 1 bandit + 1 secret = 2 total
        assert file_result["security_issues"] == 2
        # high-severity secret makes it fail
        assert file_result["security_passed"] is False


# ---------------------------------------------------------------------------
# tapps_quick_check
# ---------------------------------------------------------------------------


class TestTappsQuickCheck:
    """Tests for the tapps_quick_check lite-mode tool."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_success(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(str(f))
        assert result["success"] is True
        data = result["data"]
        assert "overall_score" in data
        assert "gate_passed" in data
        assert "security_passed" in data

    @pytest.mark.asyncio
    async def test_invalid_path(self) -> None:
        from tapps_mcp.server import tapps_quick_check

        result = await tapps_quick_check("/nonexistent/file.py")
        assert result["success"] is False
        assert result["error"]["code"] == "path_denied"

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_records_call(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        await tapps_quick_check(str(f))
        assert "tapps_quick_check" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_includes_nudges(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(str(f))
        assert "next_steps" in result["data"]
        assert "pipeline_progress" in result["data"]


# ---------------------------------------------------------------------------
# Checklist equivalence
# ---------------------------------------------------------------------------


class TestChecklistEquivalence:
    """Test that composite tools satisfy individual tool requirements."""

    def test_quick_check_satisfies_score_and_gate(self) -> None:
        CallTracker.record("tapps_quick_check")
        result = CallTracker.evaluate("feature")
        # feature requires: tapps_score_file, tapps_quality_gate
        assert result.complete is True

    def test_validate_changed_satisfies_review(self) -> None:
        CallTracker.record("tapps_validate_changed")
        result = CallTracker.evaluate("review")
        # review requires: tapps_score_file, tapps_security_scan, tapps_quality_gate
        assert result.complete is True


# ---------------------------------------------------------------------------
# batch_validator module
# ---------------------------------------------------------------------------


class TestBatchValidator:
    """Tests for the batch_validator module."""

    @patch("tapps_mcp.tools.batch_validator.subprocess.run")
    def test_detect_changed_filters_py_only(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.tools.batch_validator import detect_changed_python_files

        # Create test files
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.txt").write_text("hello\n")
        (tmp_path / "c.py").write_text("y = 2\n")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="a.py\nb.txt\nc.py\n",
        )

        result = detect_changed_python_files(tmp_path)
        assert len(result) == 2
        assert all(p.suffix == ".py" for p in result)

    @patch("tapps_mcp.tools.batch_validator.subprocess.run")
    def test_detect_changed_empty_diff(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.tools.batch_validator import detect_changed_python_files

        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = detect_changed_python_files(tmp_path)
        assert result == []

    @patch("tapps_mcp.tools.batch_validator.subprocess.run")
    def test_detect_changed_deduplicates(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.tools.batch_validator import detect_changed_python_files

        (tmp_path / "a.py").write_text("x = 1\n")

        # Both unstaged and staged return the same file
        mock_run.return_value = MagicMock(returncode=0, stdout="a.py\n")
        result = detect_changed_python_files(tmp_path)
        assert len(result) == 1

    def test_format_batch_summary(self) -> None:
        from tapps_mcp.tools.batch_validator import format_batch_summary

        results = [
            {"gate_passed": True, "security_issues": 0},
            {"gate_passed": False, "security_issues": 2},
        ]
        summary = format_batch_summary(results)
        assert "2 files" in summary
        assert "1 passed" in summary
        assert "1 failed" in summary
        assert "2 security" in summary
