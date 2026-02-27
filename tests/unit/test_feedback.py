"""Tests for feedback tracker."""

import pytest

from tapps_mcp.metrics.feedback import FeedbackTracker


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def tracker(metrics_dir):
    return FeedbackTracker(metrics_dir)


class TestFeedbackTracker:
    def test_record(self, tracker):
        entry = tracker.record(
            tool_name="tapps_score_file",
            helpful=True,
            context="Gave accurate score",
            session_id="s1",
        )
        assert entry.tool_name == "tapps_score_file"
        assert entry.helpful is True

    def test_record_not_helpful(self, tracker):
        entry = tracker.record("tapps_consult_expert", helpful=False)
        assert entry.helpful is False

    def test_get_statistics(self, tracker):
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_a", helpful=False)

        stats = tracker.get_statistics()
        assert stats["total_feedback"] == 3
        assert stats["helpful_count"] == 2
        assert stats["not_helpful_count"] == 1
        assert abs(stats["helpful_rate"] - 0.6667) < 0.01

    def test_get_statistics_by_tool(self, tracker):
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_b", helpful=False)

        stats_a = tracker.get_statistics(tool_name="tool_a")
        assert stats_a["helpful_rate"] == 1.0

        stats_b = tracker.get_statistics(tool_name="tool_b")
        assert stats_b["helpful_rate"] == 0.0

    def test_get_by_tool(self, tracker):
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_b", helpful=False)
        tracker.record("tool_a", helpful=True)

        by_tool = tracker.get_by_tool()
        assert "tool_a" in by_tool
        assert by_tool["tool_a"]["total"] == 2
        assert by_tool["tool_a"]["helpful"] == 2

    def test_empty_statistics(self, tracker):
        stats = tracker.get_statistics()
        assert stats["total_feedback"] == 0
        assert stats["helpful_rate"] == 0.0

    def test_context_truncation(self, tracker):
        long_context = "x" * 1000
        entry = tracker.record("tool_a", True, context=long_context)
        assert len(entry.context) == 500

    def test_deduplication_same_feedback_is_duplicate(self, tracker):
        """Same feedback within dedup window is detected as duplicate."""
        tracker.record("tool_a", helpful=True, context="good")
        assert tracker.is_duplicate("tool_a", True, "good") is True

    def test_deduplication_different_feedback_not_duplicate(self, tracker):
        """Different feedback is not flagged as duplicate."""
        tracker.record("tool_a", helpful=True, context="good")
        assert tracker.is_duplicate("tool_a", False, "good") is False
        assert tracker.is_duplicate("tool_b", True, "good") is False
        assert tracker.is_duplicate("tool_a", True, "different") is False

    def test_deduplication_empty_tracker_not_duplicate(self, tracker):
        """No feedback recorded means no duplicates."""
        assert tracker.is_duplicate("tool_a", True, "") is False


class TestFeedbackToolValidation:
    """Tests for the tapps_feedback tool handler validation."""

    def test_invalid_tool_name_returns_error(self):
        from tapps_mcp.server_metrics_tools import _VALID_TOOL_NAMES

        assert "tapps_score_file" in _VALID_TOOL_NAMES
        assert "nonexistent_tool" not in _VALID_TOOL_NAMES

    def test_scoring_tools_defined(self):
        from tapps_mcp.server_metrics_tools import _SCORING_TOOLS

        assert "tapps_score_file" in _SCORING_TOOLS
        assert "tapps_quality_gate" in _SCORING_TOOLS
        assert "tapps_quick_check" in _SCORING_TOOLS
        assert "tapps_feedback" not in _SCORING_TOOLS


class TestFeedbackWeightAdjustment:
    """Tests for adaptive weight adjustment triggered by feedback."""

    def test_adjust_scoring_weights_helpful(self):
        from tapps_mcp.server_metrics_tools import _adjust_scoring_weights

        result = _adjust_scoring_weights(helpful=True)
        assert result is True

    def test_adjust_scoring_weights_not_helpful(self):
        from tapps_mcp.server_metrics_tools import _adjust_scoring_weights

        result = _adjust_scoring_weights(helpful=False)
        assert result is True

    def test_adjust_scoring_weights_normalizes(self):
        """Weights should still sum to ~1.0 after adjustment."""
        from tapps_mcp.config.settings import load_settings
        from tapps_mcp.server_metrics_tools import _adjust_scoring_weights

        _adjust_scoring_weights(helpful=True)
        settings = load_settings()
        w = settings.scoring_weights
        total = w.complexity + w.security + w.maintainability + w.test_coverage + (
            w.performance + w.structure + w.devex
        )
        assert abs(total - 1.0) < 0.01


class TestStatsRecommendations:
    """Tests for _generate_stats_recommendations."""

    def test_security_scan_low_usage(self):
        from tapps_mcp.server_metrics_tools import _generate_stats_recommendations

        class FakeSummary:
            gate_pass_rate = 0.8

        breakdowns = [
            {"tool_name": "tapps_score_file", "call_count": 100, "avg_duration_ms": 50},
            {"tool_name": "tapps_security_scan", "call_count": 5, "avg_duration_ms": 30},
        ]
        recs = _generate_stats_recommendations(FakeSummary(), breakdowns)
        assert any("auto-security" in r for r in recs)

    def test_research_never_called(self):
        from tapps_mcp.server_metrics_tools import _generate_stats_recommendations

        class FakeSummary:
            gate_pass_rate = 0.8

        breakdowns = [
            {"tool_name": "tapps_score_file", "call_count": 10, "avg_duration_ms": 50},
        ]
        recs = _generate_stats_recommendations(FakeSummary(), breakdowns)
        assert any("tapps_research" in r for r in recs)

    def test_high_gate_fail_rate(self):
        from tapps_mcp.server_metrics_tools import _generate_stats_recommendations

        class FakeSummary:
            gate_pass_rate = 0.3

        breakdowns = [
            {"tool_name": "tapps_score_file", "call_count": 10, "avg_duration_ms": 50},
            {"tool_name": "tapps_research", "call_count": 2, "avg_duration_ms": 100},
            {"tool_name": "tapps_checklist", "call_count": 1, "avg_duration_ms": 50},
        ]
        recs = _generate_stats_recommendations(FakeSummary(), breakdowns)
        assert any("Quality gate failing" in r for r in recs)

    def test_checklist_never_called(self):
        from tapps_mcp.server_metrics_tools import _generate_stats_recommendations

        class FakeSummary:
            gate_pass_rate = 0.9

        breakdowns = [
            {"tool_name": "tapps_score_file", "call_count": 10, "avg_duration_ms": 50},
            {"tool_name": "tapps_research", "call_count": 2, "avg_duration_ms": 100},
            {"tool_name": "tapps_security_scan", "call_count": 5, "avg_duration_ms": 30},
        ]
        recs = _generate_stats_recommendations(FakeSummary(), breakdowns)
        assert any("tapps_checklist" in r for r in recs)

    def test_slow_validate_changed(self):
        from tapps_mcp.server_metrics_tools import _generate_stats_recommendations

        class FakeSummary:
            gate_pass_rate = 0.9

        breakdowns = [
            {"tool_name": "tapps_validate_changed", "call_count": 5, "avg_duration_ms": 90000},
            {"tool_name": "tapps_research", "call_count": 2, "avg_duration_ms": 100},
            {"tool_name": "tapps_checklist", "call_count": 1, "avg_duration_ms": 50},
            {"tool_name": "tapps_score_file", "call_count": 10, "avg_duration_ms": 50},
            {"tool_name": "tapps_security_scan", "call_count": 5, "avg_duration_ms": 30},
        ]
        recs = _generate_stats_recommendations(FakeSummary(), breakdowns)
        assert any("tapps_quick_check per-file" in r for r in recs)

    def test_no_recommendations_when_all_good(self):
        from tapps_mcp.server_metrics_tools import _generate_stats_recommendations

        class FakeSummary:
            gate_pass_rate = 0.9

        breakdowns = [
            {"tool_name": "tapps_score_file", "call_count": 10, "avg_duration_ms": 50},
            {"tool_name": "tapps_security_scan", "call_count": 5, "avg_duration_ms": 30},
            {"tool_name": "tapps_research", "call_count": 2, "avg_duration_ms": 100},
            {"tool_name": "tapps_checklist", "call_count": 1, "avg_duration_ms": 50},
        ]
        recs = _generate_stats_recommendations(FakeSummary(), breakdowns)
        assert len(recs) == 0


class TestContextSanitization:
    """Tests for context sanitization in feedback."""

    def test_sanitize_param_strips_control_chars(self):
        from tapps_mcp.server_metrics_tools import _sanitize_param

        result = _sanitize_param("hello\x00world\x1f!")
        assert result == "helloworld!"

    def test_sanitize_param_truncates(self):
        from tapps_mcp.server_metrics_tools import _sanitize_param

        result = _sanitize_param("x" * 200, max_len=100)
        assert len(result) == 100
