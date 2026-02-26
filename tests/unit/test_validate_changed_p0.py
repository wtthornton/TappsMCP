"""Tests for P0 validate_changed enhancements: security_depth + include_impact."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.project.models import FileImpact, ImpactReport
from tapps_mcp.scoring.models import ScoreResult


def _mock_score() -> ScoreResult:
    return ScoreResult(
        file_path="test.py",
        categories={},
        overall_score=85.0,
        security_issues=[],
    )


def _mock_scorer(quick: bool = True) -> MagicMock:
    scorer = MagicMock()
    score = _mock_score()
    scorer.score_file = AsyncMock(return_value=score)
    scorer.score_file_quick = MagicMock(return_value=score)
    return scorer


def _mock_impact_report(
    file_path: str = "test.py",
    severity: str = "medium",
    direct: int = 2,
    transitive: int = 1,
    tests: int = 1,
) -> ImpactReport:
    return ImpactReport(
        changed_file=file_path,
        change_type="modified",
        severity=severity,
        direct_dependents=[
            FileImpact(file_path=f"dep_{i}.py", impact_type="direct", reason="imports test")
            for i in range(direct)
        ],
        transitive_dependents=[
            FileImpact(
                file_path=f"trans_{i}.py", impact_type="transitive", reason="transitive import"
            )
            for i in range(transitive)
        ],
        test_files=[
            FileImpact(file_path=f"test_{i}.py", impact_type="test", reason="test file")
            for i in range(tests)
        ],
        total_affected=direct + transitive + tests,
    )


class TestValidateChangedP0:
    """Tests for security_depth and include_impact parameters."""

    @pytest.mark.asyncio
    async def test_security_depth_basic_quick_no_full_scan(self, tmp_path: Path) -> None:
        """security_depth='basic' + quick=True should NOT run security scan."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer = _mock_scorer()
        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.security.secret_scanner.SecretScanner"
            ) as mock_secret_scanner,
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed(
                file_paths=str(f),
                quick=True,
                security_depth="basic",
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 1
        # SecretScanner should NOT have been instantiated in quick+basic mode
        mock_secret_scanner.assert_not_called()

    @pytest.mark.asyncio
    async def test_security_depth_full_quick_runs_full_scan(self, tmp_path: Path) -> None:
        """security_depth='full' + quick=True should run security scan."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer = _mock_scorer()
        mock_gate = MagicMock(passed=True, failures=[])

        mock_secret_result = MagicMock()
        mock_secret_result.total_findings = 0
        mock_secret_result.high_severity = 0

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.security.secret_scanner.SecretScanner"
            ) as mock_secret_scanner_cls,
        ):
            mock_secret_scanner_cls.return_value.scan_file.return_value = mock_secret_result
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed(
                file_paths=str(f),
                quick=True,
                security_depth="full",
            )

        assert result["success"] is True
        assert result["data"]["files_validated"] == 1
        # SecretScanner SHOULD have been called because security_depth="full"
        mock_secret_scanner_cls.assert_called_once()

    @pytest.mark.asyncio
    async def test_include_impact_true_returns_summary(self, tmp_path: Path) -> None:
        """include_impact=True should produce an impact_summary in the response."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer = _mock_scorer()
        mock_gate = MagicMock(passed=True, failures=[])
        mock_report = _mock_impact_report(str(f), severity="medium")

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.project.impact_analyzer.build_import_graph",
                return_value={},
            ),
            patch(
                "tapps_mcp.project.impact_analyzer.analyze_impact",
                return_value=mock_report,
            ) as mock_analyze,
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed(
                file_paths=str(f),
                quick=True,
                include_impact=True,
            )

        assert result["success"] is True
        assert "impact_summary" in result["data"]
        summary = result["data"]["impact_summary"]
        assert summary["max_severity"] == "medium"
        assert summary["total_affected_files"] == 3  # 2 direct + 1 transitive
        assert len(summary["per_file"]) == 1
        mock_analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_include_impact_false_no_summary(self, tmp_path: Path) -> None:
        """include_impact=False (default) should NOT include impact_summary."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer = _mock_scorer()
        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed(
                file_paths=str(f),
                quick=True,
                include_impact=False,
            )

        assert result["success"] is True
        assert "impact_summary" not in result["data"]

    @pytest.mark.asyncio
    async def test_impact_failure_graceful(self, tmp_path: Path) -> None:
        """When analyze_impact raises, the response should still succeed with error info."""
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer = _mock_scorer()
        mock_gate = MagicMock(passed=True, failures=[])

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.project.impact_analyzer.build_import_graph",
                return_value={},
            ),
            patch(
                "tapps_mcp.project.impact_analyzer.analyze_impact",
                side_effect=RuntimeError("graph build failed"),
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed(
                file_paths=str(f),
                quick=True,
                include_impact=True,
            )

        assert result["success"] is True
        # Impact should still be present but with error info
        assert "impact_summary" in result["data"]
        impact = result["data"]["impact_summary"]
        # The per-file exception is caught individually — error appears in per_file entry
        assert len(impact["per_file"]) == 1
        assert impact["per_file"][0]["error"] is True
        assert impact["per_file"][0]["severity"] == "unknown"

    @pytest.mark.asyncio
    async def test_backward_compat_no_new_params(self, tmp_path: Path) -> None:
        """Calling with no new params should produce the same shape as before.

        Since include_impact now defaults to True, the response includes
        impact_summary with default values.
        """
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer = _mock_scorer()
        mock_gate = MagicMock(passed=True, failures=[])
        mock_report = _mock_impact_report(str(f), severity="low", direct=0, transitive=0, tests=0)

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.project.impact_analyzer.build_import_graph",
                return_value={},
            ),
            patch(
                "tapps_mcp.project.impact_analyzer.analyze_impact",
                return_value=mock_report,
            ),
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed(file_paths=str(f))

        assert result["success"] is True
        data = result["data"]
        assert "files_validated" in data
        assert "all_gates_passed" in data
        assert "total_security_issues" in data
        assert "results" in data
        assert "summary" in data
        # include_impact defaults to True so impact_summary is present
        assert "impact_summary" in data

    @pytest.mark.asyncio
    async def test_graph_reuse_builds_once(self, tmp_path: Path) -> None:
        """When include_impact=True and multiple files are validated,
        build_import_graph should be called exactly once (graph reuse).
        """
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("x = 1\n", encoding="utf-8")
        f2.write_text("y = 2\n", encoding="utf-8")

        scorer = _mock_scorer()
        mock_gate = MagicMock(passed=True, failures=[])
        mock_report = _mock_impact_report(severity="low", direct=0, transitive=0, tests=0)

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._validate_file_path", side_effect=Path),
            patch("tapps_mcp.scoring.scorer.CodeScorer", return_value=scorer),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=mock_gate),
            patch(
                "tapps_mcp.project.impact_analyzer.build_import_graph",
                return_value={},
            ) as mock_build,
            patch(
                "tapps_mcp.project.impact_analyzer.analyze_impact",
                return_value=mock_report,
            ) as mock_analyze,
        ):
            mock_settings.return_value.project_root = tmp_path
            mock_settings.return_value.tool_timeout = 30
            mock_settings.return_value.dependency_scan_enabled = False

            result = await tapps_validate_changed(
                file_paths=f"{f1},{f2}",
                quick=True,
                include_impact=True,
            )

        assert result["success"] is True
        # Graph built exactly once, not once per file
        mock_build.assert_called_once()
        # analyze_impact called once per file, each receiving the shared graph
        assert mock_analyze.call_count == 2
        for call in mock_analyze.call_args_list:
            assert call.kwargs.get("graph") == {}
