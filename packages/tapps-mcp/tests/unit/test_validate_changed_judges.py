"""Tests for validate_changed judge integration helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tapps_core.config.settings import TappsMCPSettings
from tapps_mcp.tools.validate_changed_output import (
    _append_judge_summary,
    _build_judge_summary_rows,
    _handle_no_changed_files,
    _run_judges,
    apply_judge_payload,
)


class TestJudgeSummaryRows:
    def test_pass_and_fail_rows(self) -> None:
        rows = _build_judge_summary_rows(
            [
                {"judge": "audit CLI", "result": "pass"},
                {
                    "judge": "PDF tests",
                    "result": "fail",
                    "blocking": True,
                    "message": "exit 1",
                },
                {"judge": "grep build", "result": "skipped"},
            ]
        )
        assert rows[0].startswith("PASS")
        assert rows[1].startswith("FAIL")
        assert rows[2].startswith("SKIP")


class TestApplyJudgePayload:
    def test_blocking_failure_sets_all_gates_passed_false(self) -> None:
        resp_data = {"all_gates_passed": True, "summary_rows": ["PASS  gate"]}
        payload = {
            "judges_passed": False,
            "judge_results": [
                {"judge": "audit", "result": "fail", "blocking": True, "message": "exit 2"}
            ],
        }
        summary = apply_judge_payload(resp_data, payload, summary="2/2 passed")
        assert resp_data["all_gates_passed"] is False
        assert "blocking failed" in summary
        assert len(resp_data["summary_rows"]) == 2

    def test_advisory_failure_leaves_gates_passed(self) -> None:
        resp_data = {"all_gates_passed": True, "summary_rows": []}
        payload = {
            "judges_passed": True,
            "judge_results": [{"judge": "hint", "result": "fail", "blocking": False}],
        }
        summary = _append_judge_summary("ok", payload["judge_results"])
        apply_judge_payload(resp_data, payload, summary=summary)
        assert resp_data["all_gates_passed"] is True

    def test_structured_overall_passed_follows_blocking_judges(self) -> None:
        from tapps_mcp.common.output_schemas import ValidateChangedOutput

        resp_data = {"all_gates_passed": True, "summary_rows": []}
        payload = {
            "judges_passed": False,
            "judge_results": [{"judge": "audit", "result": "fail", "blocking": True}],
        }
        apply_judge_payload(resp_data, payload, summary="ok")
        structured = ValidateChangedOutput(
            files=[],
            overall_passed=bool(resp_data["all_gates_passed"]),
            total_files=0,
            passed_count=0,
            failed_count=0,
            security_depth="basic",
        )
        assert structured.overall_passed is False


class TestHandleNoChangedFilesWithJudges:
    @pytest.mark.asyncio
    async def test_runs_judges_when_configured(self, tmp_path: Path) -> None:
        judges = [{"type": "exists", "target": "missing.txt", "blocking": True}]
        judge_payload = {
            "judges_passed": False,
            "judge_results": [
                {"judge": "exists", "result": "fail", "blocking": True, "message": "Missing"}
            ],
        }
        with (
            patch(
                "tapps_mcp.tools.validate_changed_output._run_judges",
                AsyncMock(return_value=judge_payload),
            ) as mock_run,
            patch("tapps_mcp.server_pipeline_tools._write_validate_ok_marker") as mock_marker,
        ):
            resp = await _handle_no_changed_files(
                0,
                TappsMCPSettings(project_root=tmp_path),
                lambda *_a, **_k: None,
                lambda _tool, resp: resp,
                judges=judges,
            )

        mock_run.assert_awaited_once()
        assert resp["data"]["all_gates_passed"] is False
        mock_marker.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_write_marker_when_no_files_even_if_judges_pass(
        self, tmp_path: Path
    ) -> None:
        """Zero files gated is inconclusive — never write the validate-ok marker."""
        judges = [{"type": "exists", "target": "x"}]
        with (
            patch(
                "tapps_mcp.tools.validate_changed_output._run_judges",
                AsyncMock(
                    return_value={
                        "judges_passed": True,
                        "judge_results": [{"judge": "exists", "result": "pass"}],
                    }
                ),
            ),
            patch("tapps_mcp.server_pipeline_tools._write_validate_ok_marker") as mock_marker,
        ):
            resp = await _handle_no_changed_files(
                0,
                TappsMCPSettings(project_root=tmp_path),
                lambda *_a, **_k: None,
                lambda _tool, resp: resp,
                judges=judges,
            )

        assert resp["data"]["all_gates_passed"] is False
        mock_marker.assert_not_called()


class TestRunJudgesExceptionPayload:
    @pytest.mark.asyncio
    async def test_exception_surfaces_error_result(self, tmp_path: Path) -> None:
        with patch(
            "tapps_core.metrics.judge.run_judges",
            AsyncMock(side_effect=RuntimeError("judge boom")),
        ):
            payload = await _run_judges([{"type": "exists", "target": "x"}], tmp_path)

        assert payload["judges_passed"] is False
        assert len(payload["judge_results"]) == 1
        assert payload["judge_results"][0]["result"] == "error"
        assert "judge boom" in payload["judge_results"][0]["message"]


class TestRunJudgesGitDiffWhenChanged:
    @pytest.mark.asyncio
    async def test_uses_git_diff_for_when_changed(self, tmp_path: Path) -> None:
        from tapps_core.metrics.judge import run_judges

        target = tmp_path / "brands" / "acme.yaml"
        target.parent.mkdir(parents=True)
        target.touch()

        with patch(
            "tapps_core.metrics.judge._git_changed_paths",
            return_value=["brands/acme.yaml"],
        ):
            result = await run_judges(
                [
                    {
                        "type": "exists",
                        "target": str(target),
                        "when_changed": ["brands/**"],
                        "blocking": True,
                    }
                ],
                cwd=tmp_path,
                changed_paths=None,
                base_ref="HEAD",
            )

        assert result["judge_results"][0]["result"] == "pass"
