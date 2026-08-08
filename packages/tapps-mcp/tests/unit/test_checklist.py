"""Tests for tools.checklist — session call tracking and epic validation."""

from __future__ import annotations

import pytest

from tapps_mcp.tools.checklist import (
    TASK_TOOL_MAP,
    TASK_TOOL_MAP_HIGH,
    TASK_TOOL_MAP_LOW,
    CallTracker,
    ChecklistResult,
    ToolCallRecord,
)


class TestToolCallRecord:
    def test_creation(self):
        r = ToolCallRecord(tool_name="tapps_score_file")
        assert r.tool_name == "tapps_score_file"
        assert r.timestamp > 0


class TestTaskToolMap:
    def test_feature_task(self):
        m = TASK_TOOL_MAP["feature"]
        assert "tapps_score_file" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_bugfix_task(self):
        m = TASK_TOOL_MAP["bugfix"]
        assert "tapps_score_file" in m["required"]

    def test_refactor_task(self):
        m = TASK_TOOL_MAP["refactor"]
        assert "tapps_score_file" in m["required"]
        assert "tapps_quality_gate" in m["required"]
        assert "tapps_call_graph" in m["recommended"]
        assert "tapps_diff_impact" in m["recommended"]

    def test_security_task(self):
        m = TASK_TOOL_MAP["security"]
        assert "tapps_security_scan" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_review_task(self):
        m = TASK_TOOL_MAP["review"]
        assert "tapps_score_file" in m["required"]
        assert "tapps_security_scan" in m["required"]
        assert "tapps_quality_gate" in m["required"]

    def test_all_task_types_present(self):
        expected = {
            "feature",
            "bugfix",
            "refactor",
            "security",
            "review",
            "epic",
            "release",
            "document",
            # ADR-0025 task types (qa / documentation / frontend).
            "documentation",
            "qa",
            "frontend",
        }
        assert set(TASK_TOOL_MAP.keys()) == expected

    def test_retired_tapps_memory_not_in_any_bucket(self) -> None:
        """TAP-1994: tapps_memory MCP removed — checklist must not recommend it."""
        for level_name, level_map in (
            ("medium", TASK_TOOL_MAP),
            ("high", TASK_TOOL_MAP_HIGH),
            ("low", TASK_TOOL_MAP_LOW),
        ):
            for task_type, spec in level_map.items():
                for bucket in ("required", "recommended", "optional"):
                    tools = spec.get(bucket, [])
                    assert "tapps_memory" not in tools, (
                        f"tapps_memory still in {level_name}/{task_type}/{bucket}"
                    )

    def test_document_task(self):
        m = TASK_TOOL_MAP["document"]
        assert "tapps_validate_changed" in m["required"]
        assert "tapps_validate_config" in m["recommended"]

    def test_document_task_type_resolves_without_fallback(self):
        from tapps_mcp.tools.checklist import TASK_TYPE_REASONS, CallTracker

        CallTracker.reset()
        result = CallTracker.evaluate("document", engagement_level="medium")
        assert result.resolved_policy_task_type == "document"
        assert result.policy_fallback is False
        assert result.task_type_hint == TASK_TYPE_REASONS["document"]

    def test_epic_task(self):
        m = TASK_TOOL_MAP["epic"]
        assert "tapps_checklist" in m["required"]


class TestCallTracker:
    # Tests in this class assert against the medium TASK_TOOL_MAP. They were
    # written before the high/low maps existed and historically read engagement
    # from `load_settings().llm_engagement_level`. That coupling is order-
    # dependent on CI — sibling tests that monkeypatch TAPPS_MCP_LLM_ENGAGEMENT_LEVEL
    # or call tapps_set_engagement_level() can leak HIGH/LOW into the cached
    # settings. Pass engagement_level="medium" explicitly via the helper below
    # so these assertions are independent of global state.

    @staticmethod
    def _evaluate(task_type, **kwargs):
        return CallTracker.evaluate(task_type, engagement_level="medium", **kwargs)

    def setup_method(self):
        CallTracker.reset()

    def test_record_and_get(self):
        CallTracker.record("tapps_score_file")
        assert "tapps_score_file" in CallTracker.get_called_tools()

    def test_total_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        assert CallTracker.total_calls() == 3

    def test_unique_tools(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_score_file")
        called = CallTracker.get_called_tools()
        assert called == {"tapps_score_file"}

    def test_reset(self):
        CallTracker.record("tapps_score_file")
        CallTracker.reset()
        assert CallTracker.get_called_tools() == set()
        assert CallTracker.total_calls() == 0

    def test_evaluate_complete(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        result = self._evaluate("feature")
        assert result.complete is True
        assert result.missing_required == []
        assert result.task_type == "feature"

    def test_evaluate_incomplete(self):
        result = self._evaluate("feature")
        assert result.complete is False
        assert "tapps_score_file" in result.missing_required
        assert "tapps_quality_gate" in result.missing_required

    def test_evaluate_partial(self):
        CallTracker.record("tapps_score_file")
        result = self._evaluate("feature")
        assert result.complete is False
        assert "tapps_quality_gate" in result.missing_required
        assert "tapps_score_file" not in result.missing_required

    def test_evaluate_unknown_task_defaults_to_review(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_security_scan")
        CallTracker.record("tapps_quality_gate")
        result = self._evaluate("unknown_task")
        assert result.task_type == "unknown_task"
        assert result.complete is True
        assert result.policy_fallback is True
        assert result.resolved_policy_task_type == "review"

    def test_evaluate_unknown_task_strict_raises(self):
        with pytest.raises(ValueError, match="Unknown task_type"):
            self._evaluate(
                "not_a_real_task",
                strict_unknown_task_type=True,
            )

    def test_begin_session_adopts_pre_session_calls(self):
        """Calls recorded before begin_session (empty session_id) are kept.

        Agents sometimes invoke tools before ``tapps_session_start``; dropping
        those records caused checklist false negatives.
        """
        CallTracker.record("tapps_score_file")
        CallTracker.begin_session()
        CallTracker.record("tapps_quality_gate")
        r = self._evaluate("feature")
        assert "tapps_score_file" in r.called
        assert "tapps_quality_gate" in r.called

    def test_begin_session_isolates_prior_session_calls(self):
        """Calls from a previous checklist session stay filtered out."""
        CallTracker.begin_session("sess-a")
        CallTracker.record("tapps_score_file")
        CallTracker.begin_session("sess-b")
        CallTracker.record("tapps_quality_gate")
        r = self._evaluate("feature")
        assert "tapps_score_file" not in r.called
        assert "tapps_quality_gate" in r.called

    def test_evaluate_includes_recommended(self):
        result = self._evaluate("feature")
        assert "tapps_security_scan" in result.missing_recommended

    def test_evaluate_includes_optional(self):
        result = self._evaluate("feature")
        assert "tapps_checklist" in result.missing_optional

    def test_evaluate_total_calls(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        result = self._evaluate("feature")
        assert result.total_calls == 2

    def test_evaluate_called_sorted(self):
        CallTracker.record("tapps_quality_gate")
        CallTracker.record("tapps_score_file")
        result = self._evaluate("feature")
        assert result.called == ["tapps_quality_gate", "tapps_score_file"]

    def test_evaluate_engagement_high_feature_requires_more(self):
        """High engagement: feature requires score, gate, security_scan."""
        result = CallTracker.evaluate("feature", engagement_level="high")
        assert "tapps_security_scan" in result.missing_required
        assert "tapps_score_file" in result.missing_required
        assert "tapps_quality_gate" in result.missing_required

    def test_evaluate_engagement_high_feature_complete_with_all(self):
        CallTracker.record("tapps_score_file")
        CallTracker.record("tapps_quality_gate")
        CallTracker.record("tapps_security_scan")
        result = CallTracker.evaluate("feature", engagement_level="high")
        assert result.complete is True
        assert result.missing_required == []

    def test_evaluate_engagement_low_feature_requires_less(self):
        """Low engagement: feature only requires quality_gate."""
        result = CallTracker.evaluate("feature", engagement_level="low")
        assert "tapps_quality_gate" in result.missing_required
        assert "tapps_score_file" in result.missing_recommended

    def test_evaluate_engagement_low_feature_complete_with_gate_only(self):
        CallTracker.record("tapps_quality_gate")
        result = CallTracker.evaluate("feature", engagement_level="low")
        assert result.complete is True

    def test_engagement_maps_exist(self):
        assert set(TASK_TOOL_MAP_HIGH.keys()) == set(TASK_TOOL_MAP.keys())
        assert set(TASK_TOOL_MAP_LOW.keys()) == set(TASK_TOOL_MAP.keys())
        assert "tapps_security_scan" in TASK_TOOL_MAP_HIGH["feature"]["required"]
        assert "tapps_security_scan" not in TASK_TOOL_MAP_LOW["feature"]["required"]


class TestChecklistResult:
    def test_creation(self):
        r = ChecklistResult(task_type="feature", complete=True, total_calls=5)
        assert r.task_type == "feature"
        assert r.complete is True
        assert r.total_calls == 5
        assert r.called == []
        assert r.missing_required == []
