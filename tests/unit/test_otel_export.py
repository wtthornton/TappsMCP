"""Tests for OpenTelemetry export."""


import pytest

from tapps_mcp.metrics.execution_metrics import ToolCallMetric
from tapps_mcp.metrics.otel_export import (
    export_otel_trace,
    export_to_file,
)


@pytest.fixture
def sample_metrics():
    return [
        ToolCallMetric(
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
        ),
        ToolCallMetric(
            call_id="def456",
            tool_name="tapps_quality_gate",
            status="failed",
            duration_ms=200.0,
            started_at="2025-01-01T00:00:01+00:00",
            completed_at="2025-01-01T00:00:01.200+00:00",
            error_code="timeout",
        ),
    ]


class TestExportOtelTrace:
    def test_basic_structure(self, sample_metrics):
        trace = export_otel_trace(sample_metrics)
        assert "resourceSpans" in trace
        assert len(trace["resourceSpans"]) == 1

        resource_span = trace["resourceSpans"][0]
        assert "resource" in resource_span
        assert "scopeSpans" in resource_span

    def test_span_count(self, sample_metrics):
        trace = export_otel_trace(sample_metrics)
        spans = trace["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans) == 2

    def test_span_attributes(self, sample_metrics):
        trace = export_otel_trace(sample_metrics)
        spans = trace["resourceSpans"][0]["scopeSpans"][0]["spans"]

        # First span - successful score
        span0 = spans[0]
        assert span0["name"] == "tapps_score_file"
        attrs = {a["key"]: a["value"] for a in span0["attributes"]}
        assert attrs["tool.name"]["stringValue"] == "tapps_score_file"
        assert attrs["tool.score"]["doubleValue"] == 85.0
        assert attrs["tool.gate_passed"]["boolValue"] is True

    def test_error_status(self, sample_metrics):
        trace = export_otel_trace(sample_metrics)
        spans = trace["resourceSpans"][0]["scopeSpans"][0]["spans"]

        # Second span - failed
        span1 = spans[1]
        assert span1["status"]["code"] == 2  # ERROR

    def test_service_info(self, sample_metrics):
        trace = export_otel_trace(sample_metrics)
        resource = trace["resourceSpans"][0]["resource"]
        attrs = {a["key"]: a["value"] for a in resource["attributes"]}
        assert attrs["service.name"]["stringValue"] == "tapps-mcp"

    def test_empty_metrics(self):
        trace = export_otel_trace([])
        spans = trace["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans) == 0


class TestExportToFile:
    def test_export_creates_file(self, sample_metrics, tmp_path):
        traces_dir = tmp_path / "traces"
        path = export_to_file(sample_metrics, traces_dir)
        assert path.exists()
        assert "trace_" in path.name
        assert path.suffix == ".json"

    def test_export_content_is_valid(self, sample_metrics, tmp_path):
        import json

        traces_dir = tmp_path / "traces"
        path = export_to_file(sample_metrics, traces_dir)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "resourceSpans" in data
