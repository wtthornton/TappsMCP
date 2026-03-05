"""Tests for MCP tool handlers in server.py."""

from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.gates.models import GateResult, GateThresholds
from tapps_mcp.scoring.models import CategoryScore, ScoreResult
from tapps_mcp.security.security_scanner import SecurityScanResult
from tapps_mcp.server import (
    tapps_checklist,
    tapps_quality_gate,
    tapps_score_file,
    tapps_security_scan,
    tapps_server_info,
)
from tapps_mcp.tools.checklist import CallTracker


class TestTappsServerInfo:
    def setup_method(self):
        CallTracker.reset()

    @pytest.mark.asyncio
    async def test_returns_success(self):
        result = await tapps_server_info()
        assert result["success"] is True
        assert result["tool"] == "tapps_server_info"
        assert "data" in result
        assert "server" in result["data"]
        assert result["data"]["server"]["name"] == "TappsMCP"

    @pytest.mark.asyncio
    async def test_includes_version(self):
        result = await tapps_server_info()
        assert "version" in result["data"]["server"]

    @pytest.mark.asyncio
    async def test_includes_configuration(self):
        result = await tapps_server_info()
        assert "configuration" in result["data"]
        assert "project_root" in result["data"]["configuration"]

    @pytest.mark.asyncio
    async def test_records_call(self):
        CallTracker.reset()
        await tapps_server_info()
        assert "tapps_server_info" in CallTracker.get_called_tools()


class TestTappsScoreFile:
    def setup_method(self):
        CallTracker.reset()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.scoring.scorer.CodeScorer.score_file_quick")
    async def test_quick_mode(self, mock_quick, mock_validate, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f

        mock_quick.return_value = ScoreResult(
            file_path=str(f),
            categories={
                "linting": CategoryScore(name="linting", score=10.0, weight=1.0),
            },
            overall_score=100.0,
        )

        result = await tapps_score_file(str(f), quick=True)
        assert result["success"] is True
        assert result["data"]["overall_score"] == 100.0
        mock_quick.assert_called_once()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.scoring.scorer.CodeScorer.score_file", new_callable=AsyncMock)
    async def test_full_mode(self, mock_full, mock_validate, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f

        mock_full.return_value = ScoreResult(
            file_path=str(f),
            categories={
                "security": CategoryScore(name="security", score=9.0, weight=0.2),
            },
            overall_score=85.0,
        )

        result = await tapps_score_file(str(f))
        assert result["success"] is True
        assert result["data"]["overall_score"] == 85.0

    @pytest.mark.asyncio
    async def test_invalid_path(self):
        result = await tapps_score_file("/nonexistent/path/file.py")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_records_call(self):
        CallTracker.reset()
        # Even if path validation fails, call should be recorded
        await tapps_score_file("/nonexistent/path.py")
        assert "tapps_score_file" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.scoring.scorer.CodeScorer.score_file_quick")
    @patch("tapps_mcp.tools.ruff.run_ruff_fix")
    async def test_quick_with_fix(self, mock_fix, mock_quick, mock_validate, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_fix.return_value = 3

        mock_quick.return_value = ScoreResult(
            file_path=str(f),
            categories={
                "linting": CategoryScore(name="linting", score=10.0, weight=1.0),
            },
            overall_score=100.0,
        )

        result = await tapps_score_file(str(f), quick=True, fix=True)
        assert result["success"] is True
        assert result["data"]["fixes_applied"] == 3
        mock_fix.assert_called_once()


class TestTappsSecurityScan:
    def setup_method(self):
        CallTracker.reset()

    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.security.security_scanner.run_security_scan")
    def test_clean_file(self, mock_scan, mock_validate, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_scan.return_value = SecurityScanResult()

        result = tapps_security_scan(str(f))
        assert result["success"] is True
        assert result["data"]["passed"] is True

    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.security.security_scanner.run_security_scan")
    def test_with_issues(self, mock_scan, mock_validate, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_scan.return_value = SecurityScanResult(
            total_issues=2,
            high_count=1,
            passed=False,
            bandit_available=True,
        )

        result = tapps_security_scan(str(f))
        assert result["success"] is True
        assert result["data"]["passed"] is False
        assert result["data"]["total_issues"] == 2

    def test_invalid_path(self):
        result = tapps_security_scan("/nonexistent/path.py")
        assert result["success"] is False

    def test_records_call(self):
        CallTracker.reset()
        tapps_security_scan("/nonexistent/path.py")
        assert "tapps_security_scan" in CallTracker.get_called_tools()


class TestTappsQualityGate:
    def setup_method(self):
        CallTracker.reset()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.scoring.scorer.CodeScorer.score_file", new_callable=AsyncMock)
    @patch("tapps_mcp.gates.evaluator.evaluate_gate")
    async def test_passing_gate(self, mock_gate, mock_score, mock_validate, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f

        mock_score.return_value = ScoreResult(
            file_path=str(f),
            categories={},
            overall_score=85.0,
        )
        mock_gate.return_value = GateResult(
            passed=True,
            scores={"overall": 85.0},
            thresholds=GateThresholds(),
            preset="standard",
        )

        result = await tapps_quality_gate(str(f))
        assert result["success"] is True
        assert result["data"]["passed"] is True

    @pytest.mark.asyncio
    async def test_invalid_path(self):
        result = await tapps_quality_gate("/nonexistent/path.py")
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_records_call(self):
        CallTracker.reset()
        await tapps_quality_gate("/nonexistent/path.py")
        assert "tapps_quality_gate" in CallTracker.get_called_tools()


class TestTappsChecklist:
    def setup_method(self):
        CallTracker.reset()

    @pytest.mark.asyncio
    async def test_empty_session(self):
        result = await tapps_checklist()
        assert result["success"] is True
        assert result["data"]["task_type"] == "review"
        assert result["data"]["complete"] is False

    @pytest.mark.asyncio
    async def test_with_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_security_scan")
        CallTracker.record("tapps_quality_gate")
        result = await tapps_checklist("review")
        assert result["data"]["complete"] is True

    @pytest.mark.asyncio
    async def test_feature_task_type(self):
        result = await tapps_checklist("feature")
        assert result["data"]["task_type"] == "feature"

    @pytest.mark.asyncio
    async def test_records_self(self):
        CallTracker.reset()
        await tapps_checklist()
        assert "tapps_checklist" in CallTracker.get_called_tools()
