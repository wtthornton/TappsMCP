"""Tests for server_checklist_tools — checklist formatting and response-assembly helpers.

End-to-end behavior of ``tapps_checklist`` (auto_run, usage-gap hard-gate, TDD
stages) is covered by test_checklist_auto_run.py and test_contract_finish_gate.py;
this file focuses on the pure/isolated helper functions extracted from it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.server_checklist_tools import (
    _apply_validation_note,
    _attach_checklist_structured_output,
    _checklist_compact_format,
    _checklist_fallback_response,
    _checklist_json_format,
    _finish_task_tip,
    _format_checklist_response,
    _optional_otel_trace_hint,
)

pytestmark = [pytest.mark.usefixtures("no_repo_wide_scans"), pytest.mark.usefixtures("envelope_guard")]


def _checklist_result(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "task_type": "feature",
        "resolved_policy_task_type": "feature",
        "policy_fallback": False,
        "checklist_policy_version": "v1",
        "complete": True,
        "called": ["a", "b"],
        "total_calls": 4,
        "required_tool_names": ["a", "b"],
        "recommended_tool_names": ["c"],
        "optional_tool_names": [],
        "satisfied_required_tools": ["a", "b"],
        "satisfied_recommended_tools": ["c"],
        "satisfied_optional_tools": [],
        "missing_required": [],
        "missing_recommended": [],
        "missing_optional": [],
        "missing_required_hints": [],
        "missing_recommended_hints": [],
        "missing_optional_hints": [],
        "model_dump": lambda: {"task_type": "feature"},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestFinishTaskTip:
    def test_incomplete_tip_mentions_finish_task(self) -> None:
        assert "/tapps-finish-task" in _finish_task_tip(_checklist_result(complete=False))

    def test_complete_tip_is_the_next_time_variant(self) -> None:
        assert _finish_task_tip(_checklist_result(complete=True)).startswith("TIP:")


class TestChecklistFormats:
    def test_json_format_counts_and_next_steps(self) -> None:
        data = _checklist_json_format(
            _checklist_result(),
            {},
            checklist_session_id="sess-1",
            trace_hint=None,
        )
        assert data["required"]["total"] == 2
        assert data["required"]["satisfied"] == ["a", "b"]
        assert data["checklist_session_id"] == "sess-1"
        assert data["next_steps"]

    def test_json_format_includes_auto_run_results(self) -> None:
        data = _checklist_json_format(
            _checklist_result(),
            {"validate_changed": {"success": True}},
            checklist_session_id=None,
            trace_hint=None,
        )
        assert data["auto_run_results"]["validate_changed"]["success"] is True

    def test_json_priority_actions_capped_at_three(self) -> None:
        data = _checklist_json_format(
            _checklist_result(missing_required=["a", "b", "c", "d"]),
            {},
            checklist_session_id=None,
            trace_hint=None,
        )
        assert len(data["priority_actions"]) == 3

    def test_compact_format_summary_line(self) -> None:
        data = _checklist_compact_format(
            _checklist_result(),
            {},
            checklist_session_id=None,
            trace_hint=None,
        )
        assert data["summary"].startswith("Checklist feature:")
        assert "required 2/2 satisfied" in data["summary"]

    def test_compact_format_lists_missing(self) -> None:
        data = _checklist_compact_format(
            _checklist_result(
                complete=False,
                missing_required=["tapps_quality_gate"],
                satisfied_required_tools=["a"],
            ),
            {},
            checklist_session_id=None,
            trace_hint=None,
        )
        assert "tapps_quality_gate" in data["summary"]


class TestFormatChecklistResponse:
    def test_dispatches_to_json(self) -> None:
        data = _format_checklist_response(
            "json", _checklist_result(), {}, session_id=None, trace_hint=None
        )
        assert "required" in data

    def test_dispatches_to_compact(self) -> None:
        data = _format_checklist_response(
            "compact", _checklist_result(), {}, session_id=None, trace_hint=None
        )
        assert "summary" in data

    def test_markdown_falls_back_to_model_dump(self) -> None:
        data = _format_checklist_response(
            "markdown", _checklist_result(), {}, session_id=None, trace_hint=None
        )
        assert data == {"task_type": "feature"}

    def test_markdown_includes_auto_run_results_when_present(self) -> None:
        data = _format_checklist_response(
            "markdown",
            _checklist_result(),
            {"validate_changed": {"success": True}},
            session_id=None,
            trace_hint=None,
        )
        assert data["auto_run_results"]["validate_changed"]["success"] is True


class TestOptionalOtelTraceHint:
    def test_none_when_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("TAPPS_OTEL_TRACE_ID", raising=False)
        monkeypatch.delenv("TAPPS_OTEL_SPAN_ID", raising=False)
        assert _optional_otel_trace_hint() is None

    def test_returns_ids_when_set(self, monkeypatch) -> None:
        monkeypatch.setenv("TAPPS_OTEL_TRACE_ID", "abc")
        monkeypatch.setenv("TAPPS_OTEL_SPAN_ID", "def")
        assert _optional_otel_trace_hint() == {"trace_id": "abc", "span_id": "def"}


class TestApplyValidationNote:
    def test_noop_when_no_validation_note(self) -> None:
        resp_data: dict[str, Any] = {"next_steps": ["existing"]}
        _apply_validation_note(resp_data, {})
        assert resp_data["next_steps"] == ["existing"]

    def test_appends_note_when_present(self) -> None:
        resp_data: dict[str, Any] = {"next_steps": ["existing"]}
        auto_run_results = {"validate_changed": {"validation_note": "0 files validated"}}
        _apply_validation_note(resp_data, auto_run_results)
        assert any("0 files" in s for s in resp_data["next_steps"])

    def test_handles_missing_next_steps_key(self) -> None:
        resp_data: dict[str, Any] = {}
        auto_run_results = {"validate_changed": {"validation_note": "0 files validated"}}
        _apply_validation_note(resp_data, auto_run_results)
        assert len(resp_data["next_steps"]) == 1


class TestAttachChecklistStructuredOutput:
    def test_compact_format_is_skipped(self) -> None:
        resp: dict[str, Any] = {}
        _attach_checklist_structured_output(resp, _checklist_result(), None, {}, "compact")
        assert "structuredContent" not in resp

    def test_markdown_attaches_structured_content(self) -> None:
        resp: dict[str, Any] = {}
        _attach_checklist_structured_output(resp, _checklist_result(), "sess-1", {}, "markdown")
        assert "structuredContent" in resp

    def test_malformed_result_does_not_raise(self) -> None:
        resp: dict[str, Any] = {}
        _attach_checklist_structured_output(resp, SimpleNamespace(), None, {}, "json")
        assert "structuredContent" not in resp


class TestChecklistFallbackResponse:
    def test_returns_unavailable_marker(self) -> None:
        with (
            patch("tapps_mcp.server._record_execution"),
            patch("tapps_mcp.server._with_nudges", side_effect=lambda _name, resp, _n: resp),
        ):
            resp = _checklist_fallback_response("feature", start=0)

        assert resp["data"]["checklist_unavailable"] is True
        assert resp["data"]["complete"] is False
        assert resp["data"]["task_type"] == "feature"
