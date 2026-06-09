"""Tests for execution metrics collector."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_core.metrics.execution_metrics import (
    ToolCallMetric,
    ToolCallMetricsCollector,
)


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def collector(metrics_dir):
    return ToolCallMetricsCollector(metrics_dir)


class TestToolCallMetric:
    def test_to_dict_roundtrip(self):
        metric = ToolCallMetric(
            call_id="abc123",
            tool_name="tapps_score_file",
            status="success",
            duration_ms=150.0,
            started_at="2025-01-01T00:00:00+00:00",
            completed_at="2025-01-01T00:00:00.150+00:00",
            file_path="/tmp/test.py",
            gate_passed=True,
            score=85.0,
            session_id="sess1",
        )
        d = metric.to_dict()
        restored = ToolCallMetric.from_dict(d)
        assert restored.tool_name == "tapps_score_file"
        assert restored.score == 85.0
        assert restored.gate_passed is True

    def test_from_dict_ignores_extra_keys(self):
        data = {
            "call_id": "x",
            "tool_name": "test",
            "status": "success",
            "duration_ms": 10.0,
            "started_at": "",
            "completed_at": "",
            "extra_key": "ignored",
        }
        metric = ToolCallMetric.from_dict(data)
        assert metric.tool_name == "test"


class TestToolCallMetricsCollector:
    def test_record_and_get_recent(self, collector):
        now = datetime.now(tz=UTC)
        collector.record(
            tool_name="tapps_score_file",
            started_at=now,
            completed_at=now + timedelta(milliseconds=100),
            status="success",
            score=80.0,
        )
        recent = collector.get_recent(limit=10)
        assert len(recent) == 1
        assert recent[0].tool_name == "tapps_score_file"
        assert recent[0].score == 80.0

    def test_record_creates_daily_file(self, collector, metrics_dir):
        now = datetime.now(tz=UTC)
        collector.record(
            tool_name="test_tool",
            started_at=now,
            completed_at=now + timedelta(milliseconds=50),
        )
        files = list(metrics_dir.glob("tool_calls_*.jsonl"))
        assert len(files) == 1

    def test_get_recent_from_disk(self, collector):
        """get_recent_from_disk loads from JSONL files (not in-memory buffer)."""
        now = datetime.now(tz=UTC)
        collector.record(
            tool_name="tapps_score_file",
            started_at=now,
            completed_at=now + timedelta(milliseconds=100),
            file_path=str(collector._metrics_dir.parent / "src" / "main.py"),
        )
        # get_recent_from_disk reads from disk; should find the record
        recent = collector.get_recent_from_disk(limit=10)
        assert len(recent) >= 1
        scored = [m for m in recent if m.tool_name == "tapps_score_file"]
        assert len(scored) >= 1
        assert scored[0].file_path is not None

    def test_get_metrics_filters_by_tool(self, collector):
        now = datetime.now(tz=UTC)
        collector.record("tool_a", now, now + timedelta(milliseconds=10))
        collector.record("tool_b", now, now + timedelta(milliseconds=20))
        collector.record("tool_a", now, now + timedelta(milliseconds=30))

        results = collector.get_metrics(tool_name="tool_a")
        assert len(results) == 2

    def test_get_metrics_filters_by_status(self, collector):
        now = datetime.now(tz=UTC)
        collector.record("tool_a", now, now + timedelta(milliseconds=10), status="success")
        collector.record("tool_a", now, now + timedelta(milliseconds=10), status="failed")

        results = collector.get_metrics(status="failed")
        assert len(results) == 1
        assert results[0].status == "failed"

    def test_get_metrics_filters_by_session(self, collector):
        now = datetime.now(tz=UTC)
        collector.record("tool_a", now, now + timedelta(milliseconds=10), session_id="s1")
        collector.record("tool_a", now, now + timedelta(milliseconds=10), session_id="s2")

        results = collector.get_metrics(session_id="s1")
        assert len(results) == 1

    def test_get_summary(self, collector):
        now = datetime.now(tz=UTC)
        for i in range(5):
            collector.record(
                "test_tool",
                now,
                now + timedelta(milliseconds=100 * (i + 1)),
                status="success" if i < 4 else "failed",
                score=70.0 + i * 5,
                gate_passed=i < 3,
            )

        summary = collector.get_summary()
        assert summary.total_calls == 5
        assert summary.success_count == 4
        assert summary.failed_count == 1
        assert summary.success_rate == 0.8
        assert summary.avg_score is not None
        assert summary.gate_pass_rate is not None

    def test_get_summary_by_tool(self, collector):
        now = datetime.now(tz=UTC)
        collector.record("tool_a", now, now + timedelta(milliseconds=10))
        collector.record("tool_b", now, now + timedelta(milliseconds=20))
        collector.record("tool_a", now, now + timedelta(milliseconds=30))

        breakdowns = collector.get_summary_by_tool()
        assert len(breakdowns) == 2
        names = [b.tool_name for b in breakdowns]
        assert "tool_a" in names
        assert "tool_b" in names

    def test_cleanup_old_metrics(self, collector, metrics_dir):
        # Create a fake old file
        old_date = (datetime.now(tz=UTC) - timedelta(days=100)).strftime("%Y-%m-%d")
        old_file = metrics_dir / f"tool_calls_{old_date}.jsonl"
        old_file.write_text("{}", encoding="utf-8")

        removed = collector.cleanup_old_metrics(days_to_keep=90)
        assert removed == 1
        assert not old_file.exists()

    def test_empty_summary(self, collector):
        summary = collector.get_summary()
        assert summary.total_calls == 0
        assert summary.success_rate == 0.0

    def test_p95_duration(self, collector):
        now = datetime.now(tz=UTC)
        for i in range(20):
            collector.record("test", now, now + timedelta(milliseconds=i * 10))

        summary = collector.get_summary()
        assert summary.p95_duration_ms > 0


class TestBrainTelemetryDualWrite:
    @pytest.mark.asyncio
    async def test_record_call_emits_quality_metric_when_loop_running(
        self, collector: ToolCallMetricsCollector
    ) -> None:
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={"recorded": True})
        mock_bridge.save = AsyncMock(return_value={"success": True})
        metric = ToolCallMetric(
            call_id="abc",
            tool_name="tapps_score_file",
            status="success",
            duration_ms=12.0,
            started_at="2025-01-01T00:00:00+00:00",
            completed_at="2025-01-01T00:00:00.012+00:00",
            file_path="/tmp/x.py",
            score=88.0,
        )
        with patch(
            "tapps_core.brain_bridge.create_brain_bridge",
            return_value=mock_bridge,
        ):
            collector.record_call(metric)
            await asyncio.sleep(0)
        mock_bridge.record_kg_event.assert_awaited_once()
        kwargs = mock_bridge.record_kg_event.await_args.kwargs
        assert kwargs["event_type"] == "quality_metric"
        assert kwargs["payload_data"]["score"] == 88.0
        assert kwargs["payload_data"]["subject_key"] == "/tmp/x.py"
        assert kwargs["edges"] is None
        assert kwargs["entities"] == [
            {"entity_type": "file", "canonical_name": "/tmp/x.py"},
            {"entity_type": "tool", "canonical_name": "tapps_score_file"},
        ]
        mock_bridge.save.assert_not_awaited()

    def test_brain_storage_mode_skips_disk_write(self, metrics_dir, monkeypatch):
        monkeypatch.setenv("TAPPS_METRICS_STORAGE", "brain")
        collector = ToolCallMetricsCollector(metrics_dir)
        now = datetime.now(tz=UTC)
        collector.record("tapps_score_file", now, now + timedelta(milliseconds=5), score=90.0)
        assert list(metrics_dir.glob("tool_calls_*.jsonl")) == []
        summary = collector.get_summary()
        assert summary.total_calls == 1

    @pytest.mark.asyncio
    async def test_load_tool_call_metrics_from_brain_query_events(self):
        from tapps_core.metrics.brain_telemetry import load_tool_call_metrics_from_brain

        payload = ToolCallMetric(
            call_id="xyz",
            tool_name="tapps_quality_gate",
            status="success",
            duration_ms=5.0,
            started_at="2025-06-01T00:00:00+00:00",
            completed_at="2025-06-01T00:00:00.005+00:00",
            score=77.0,
        ).to_dict()
        mock_bridge = MagicMock()
        mock_bridge.query_events = AsyncMock(
            return_value=[{"event_type": "quality_metric", "payload": payload}]
        )
        with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=mock_bridge):
            loaded = await load_tool_call_metrics_from_brain(limit=10)
        assert len(loaded) == 1
        assert loaded[0].call_id == "xyz"
        assert loaded[0].score == 77.0
        mock_bridge.query_events.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_load_tool_call_metrics_falls_back_to_memory_search(self):
        from tapps_core.metrics.brain_telemetry import load_tool_call_metrics_from_brain

        payload = ToolCallMetric(
            call_id="legacy",
            tool_name="tapps_score_file",
            status="success",
            duration_ms=5.0,
            started_at="2025-06-01T00:00:00+00:00",
            completed_at="2025-06-01T00:00:00.005+00:00",
        ).to_dict()
        mock_bridge = MagicMock()
        mock_bridge.query_events = AsyncMock(return_value=[])
        mock_bridge.search = AsyncMock(
            return_value=[
                {
                    "key": "metrics:tool_call:legacy",
                    "value": __import__("json").dumps(payload),
                }
            ]
        )
        with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=mock_bridge):
            loaded = await load_tool_call_metrics_from_brain(limit=10)
        assert len(loaded) == 1
        assert loaded[0].call_id == "legacy"
