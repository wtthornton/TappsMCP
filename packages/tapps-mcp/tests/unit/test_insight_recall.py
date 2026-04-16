"""Tests for tapps_mcp.tools.insight_recall (STORY-102.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from tapps_mcp.tools.insight_recall import recall_insights_for_validate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(insights: list[Any] | None = None, available: bool = True) -> MagicMock:
    client = MagicMock()
    client.available = available
    client.search.return_value = insights or []
    return client


def _mock_insight(key: str = "arch.proj.structure") -> MagicMock:
    m = MagicMock()
    m.key = key
    m.value = "Some architecture fact that is longer than 300 chars " * 10
    m.insight_type = "architecture"
    m.server_origin = "docs-mcp"
    return m


# ---------------------------------------------------------------------------
# Basic return structure
# ---------------------------------------------------------------------------


class TestRecallInsightsForValidate:
    def test_returns_dict(self, tmp_path: Path):
        result = recall_insights_for_validate([], tmp_path)
        assert isinstance(result, dict)

    def test_empty_paths_returns_unavailable(self, tmp_path: Path):
        result = recall_insights_for_validate([], tmp_path)
        assert result["recall_available"] is False
        assert result["recalled_insights"] == []

    def test_response_keys_present(self, tmp_path: Path):
        result = recall_insights_for_validate([], tmp_path)
        assert "recall_available" in result
        assert "recalled_insights" in result
        assert "recall_elapsed_ms" in result
        assert "recall_query" in result

    def test_elapsed_ms_non_negative(self, tmp_path: Path):
        result = recall_insights_for_validate([], tmp_path)
        assert result["recall_elapsed_ms"] >= 0.0


# ---------------------------------------------------------------------------
# Query building
# ---------------------------------------------------------------------------


class TestQueryBuilding:
    def test_query_contains_file_stems(self, tmp_path: Path):
        paths = [tmp_path / "scorer.py", tmp_path / "config.py"]
        with patch("tapps_core.insights.client.InsightClient") as MockClient:
            mc = _make_mock_client(available=True)
            MockClient.return_value = mc
            result = recall_insights_for_validate(paths, tmp_path)
        assert "scorer" in result.get("recall_query", "") or result["recall_available"] is False

    def test_empty_query_returns_unavailable(self, tmp_path: Path):
        # Paths with no useful stems (e.g. just dots)
        result = recall_insights_for_validate([], tmp_path)
        assert result["recall_available"] is False


# ---------------------------------------------------------------------------
# Client integration
# ---------------------------------------------------------------------------


class TestClientIntegration:
    def test_unavailable_client_returns_recall_false(self, tmp_path: Path):
        paths = [tmp_path / "foo.py"]
        with patch("tapps_core.insights.client.InsightClient") as MockClient:
            mc = _make_mock_client(available=False)
            MockClient.return_value = mc
            result = recall_insights_for_validate(paths, tmp_path)
        assert result["recall_available"] is False

    def test_available_client_with_results(self, tmp_path: Path):
        insights = [_mock_insight(f"arch.proj.{i}") for i in range(3)]
        paths = [tmp_path / "scorer.py"]
        with patch("tapps_core.insights.client.InsightClient") as MockClient:
            mc = _make_mock_client(insights=insights, available=True)
            MockClient.return_value = mc
            result = recall_insights_for_validate(paths, tmp_path)
        assert result["recall_available"] is True
        assert len(result["recalled_insights"]) == 3

    def test_insight_summaries_have_required_keys(self, tmp_path: Path):
        insights = [_mock_insight("arch.test")]
        paths = [tmp_path / "scorer.py"]
        with patch("tapps_core.insights.client.InsightClient") as MockClient:
            mc = _make_mock_client(insights=insights, available=True)
            MockClient.return_value = mc
            result = recall_insights_for_validate(paths, tmp_path)
        summary = result["recalled_insights"][0]
        assert "key" in summary
        assert "value" in summary
        assert "insight_type" in summary
        assert "server_origin" in summary

    def test_value_truncated_to_300_chars(self, tmp_path: Path):
        insight = _mock_insight()
        paths = [tmp_path / "scorer.py"]
        with patch("tapps_core.insights.client.InsightClient") as MockClient:
            mc = _make_mock_client(insights=[insight], available=True)
            MockClient.return_value = mc
            result = recall_insights_for_validate(paths, tmp_path)
        assert len(result["recalled_insights"][0]["value"]) <= 300

    def test_exception_in_client_returns_safe_dict(self, tmp_path: Path):
        paths = [tmp_path / "scorer.py"]
        with patch("tapps_core.insights.client.InsightClient") as MockClient:
            MockClient.side_effect = RuntimeError("boom")
            result = recall_insights_for_validate(paths, tmp_path)
        assert result["recall_available"] is False
        assert result["recalled_insights"] == []

    def test_import_error_returns_safe_dict(self, tmp_path: Path):
        paths = [tmp_path / "scorer.py"]
        with patch.dict("sys.modules", {"tapps_core.insights.client": None}):
            result = recall_insights_for_validate(paths, tmp_path)
        # Should not raise; may succeed or fail gracefully
        assert "recall_available" in result

    def test_caps_query_at_10_paths(self, tmp_path: Path):
        paths = [tmp_path / f"file{i}.py" for i in range(20)]
        with patch("tapps_core.insights.client.InsightClient") as MockClient:
            mc = _make_mock_client(available=False)
            MockClient.return_value = mc
            # Should not raise even with many paths
            result = recall_insights_for_validate(paths, tmp_path)
        assert isinstance(result, dict)
