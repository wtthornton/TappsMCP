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

    def _test_research_never_called_REMOVED(self):
        """tapps_research removed (EPIC-94)."""

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


# ---------------------------------------------------------------------------
# Domain weight adjustment tests (Epic 57, Story 57.3)
# ---------------------------------------------------------------------------


class TestDomainWeightAdjustment:
    """Tests for domain routing weight adjustment via feedback."""

    @pytest.fixture(autouse=True)
    def setup_project_root(self, tmp_path, monkeypatch):
        """Set up a temporary project root for testing."""
        from tapps_core.config.settings import _reset_settings_cache

        _reset_settings_cache()

        # Create minimal settings for the test
        settings_file = tmp_path / ".tapps-mcp.yaml"
        settings_file.write_text("llm_engagement_level: medium\n")

        # Monkeypatch to use tmp_path as project root
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        _reset_settings_cache()

        yield

        _reset_settings_cache()

    def _test_expert_tools_defined_REMOVED(self):
        """Expert tools removed (EPIC-94)."""

    def test_adjust_domain_weights_technical(self, tmp_path):
        """Technical domain feedback should update technical weights."""
        from tapps_mcp.server_metrics_tools import _adjust_domain_weights

        success, domain_type = _adjust_domain_weights("security", helpful=True)
        assert success is True
        assert domain_type == "technical"

    def test_adjust_domain_weights_unknown(self, tmp_path):
        """Unknown domain is treated as technical after expert removal (EPIC-94)."""
        from tapps_mcp.server_metrics_tools import _adjust_domain_weights

        success, domain_type = _adjust_domain_weights("acme-billing", helpful=True)
        assert success is True
        assert domain_type == "technical"

    def test_adjust_domain_weights_persists(self, tmp_path):
        """Domain weight adjustment should persist to disk."""
        from tapps_core.adaptive.persistence import DomainWeightStore
        from tapps_core.config.settings import load_settings
        from tapps_mcp.server_metrics_tools import _adjust_domain_weights

        _adjust_domain_weights("security", helpful=True)

        settings = load_settings()
        store = DomainWeightStore(settings.project_root)
        entry = store.get_weight("security", domain_type="technical")

        assert entry is not None
        assert entry.samples == 1
        assert entry.positive_count == 1

    def test_adjust_domain_weights_negative(self, tmp_path):
        """Negative feedback should decrease weight."""
        from tapps_core.adaptive.persistence import DomainWeightStore
        from tapps_core.config.settings import load_settings
        from tapps_mcp.server_metrics_tools import _adjust_domain_weights

        # First set a baseline
        _adjust_domain_weights("testing-strategies", helpful=True)

        settings = load_settings()
        store = DomainWeightStore(settings.project_root)
        initial_entry = store.get_weight("testing-strategies", domain_type="technical")
        initial_weight = initial_entry.weight if initial_entry else 1.0

        # Now negative feedback
        _adjust_domain_weights("testing-strategies", helpful=False)

        final_entry = store.get_weight("testing-strategies", domain_type="technical")
        assert final_entry is not None
        assert final_entry.weight < initial_weight
        assert final_entry.negative_count == 1

    def test_adjust_domain_weights_multiple_feedback(self, tmp_path):
        """Multiple feedback should accumulate."""
        from tapps_core.adaptive.persistence import DomainWeightStore
        from tapps_core.config.settings import load_settings
        from tapps_mcp.server_metrics_tools import _adjust_domain_weights

        _adjust_domain_weights("security", helpful=True)
        _adjust_domain_weights("security", helpful=True)
        _adjust_domain_weights("security", helpful=False)

        settings = load_settings()
        store = DomainWeightStore(settings.project_root)
        entry = store.get_weight("security", domain_type="technical")

        assert entry is not None
        assert entry.samples == 3
        assert entry.positive_count == 2
        assert entry.negative_count == 1

    # Note: test_registered_business_domain removed — ExpertConfig/ExpertRegistry
    # were removed in EPIC-94 (expert system removal).


class TestFeedbackDomainIntegration:
    """Integration tests for domain feedback in tapps_feedback tool."""

    def test_feedback_with_domain_returns_domain_type(self, tmp_path, monkeypatch):
        """Feedback with domain should include domain_type in response."""
        from tapps_core.config.settings import _reset_settings_cache

        _reset_settings_cache()
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        _reset_settings_cache()

        # We can't easily call tapps_feedback directly due to dependencies,
        # but we can verify the _adjust_domain_weights returns correct values
        from tapps_mcp.server_metrics_tools import _adjust_domain_weights

        success, domain_type = _adjust_domain_weights("security", helpful=True)
        assert domain_type in ("technical", "business")

        _reset_settings_cache()

    def test_feedback_domain_sanitization(self):
        """Domain parameter should be sanitized."""
        from tapps_mcp.server_metrics_tools import _sanitize_param

        # Domain with control characters
        sanitized = _sanitize_param("acme\x00-billing\x1f", max_len=100)
        assert sanitized == "acme-billing"

        # Long domain name
        long_domain = "a" * 200
        sanitized = _sanitize_param(long_domain, max_len=100)
        assert len(sanitized) == 100
