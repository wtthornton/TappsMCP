"""Tests for validate_changed judge integration helpers."""

from __future__ import annotations

from tapps_mcp.tools.validate_changed_output import (
    _append_judge_summary,
    _build_judge_summary_rows,
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
