"""OpenTelemetry trace export.

Converts tool call metrics to OTEL resourceSpans format for
integration with external observability tools (Grafana, Datadog, etc.).
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path  # noqa: TC003
from typing import Any

import structlog

from tapps_core.metrics.execution_metrics import ToolCallMetric  # noqa: TC001

logger = structlog.get_logger(__name__)

# OTEL service name and version
_SERVICE_NAME = "tapps-mcp"
_SERVICE_VERSION = "0.1.0"


def _to_nanos(iso_str: str) -> int:
    """Convert ISO datetime string to nanoseconds since epoch."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return int(dt.timestamp() * 1_000_000_000)
    except (ValueError, TypeError):
        return 0


def _status_code(status: str) -> int:
    """Map tool call status to OTEL status code."""
    if status == "success":
        return 1  # STATUS_CODE_OK
    if status in ("failed", "timeout"):
        return 2  # STATUS_CODE_ERROR
    return 0  # STATUS_CODE_UNSET


def export_otel_trace(metrics: list[ToolCallMetric]) -> dict[str, Any]:
    """Convert tool call metrics to OTEL trace format.

    Returns a dict conforming to OTLP JSON trace export format:
    ``{ "resourceSpans": [...] }``

    Each tool call becomes a span with attributes for tool name,
    duration, status, file path, score, and gate result.
    """
    trace_id = uuid.uuid4().hex

    spans: list[dict[str, Any]] = []
    for metric in metrics:
        span_id = uuid.uuid4().hex[:16]

        attributes: list[dict[str, Any]] = [
            {"key": "tool.name", "value": {"stringValue": metric.tool_name}},
            {"key": "tool.status", "value": {"stringValue": metric.status}},
            {"key": "tool.duration_ms", "value": {"doubleValue": metric.duration_ms}},
            {"key": "tool.degraded", "value": {"boolValue": metric.degraded}},
        ]

        if metric.file_path:
            attributes.append({"key": "tool.file_path", "value": {"stringValue": metric.file_path}})
        if metric.score is not None:
            attributes.append({"key": "tool.score", "value": {"doubleValue": metric.score}})
        if metric.gate_passed is not None:
            attributes.append(
                {"key": "tool.gate_passed", "value": {"boolValue": metric.gate_passed}}
            )
        if metric.error_code:
            attributes.append(
                {"key": "tool.error_code", "value": {"stringValue": metric.error_code}}
            )
        if metric.session_id:
            attributes.append({"key": "session.id", "value": {"stringValue": metric.session_id}})

        span = {
            "traceId": trace_id,
            "spanId": span_id,
            "name": metric.tool_name,
            "kind": 1,  # SPAN_KIND_INTERNAL
            "startTimeUnixNano": _to_nanos(metric.started_at),
            "endTimeUnixNano": _to_nanos(metric.completed_at),
            "status": {
                "code": _status_code(metric.status),
                "message": metric.error_code or "",
            },
            "attributes": attributes,
        }
        spans.append(span)

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "service.name",
                            "value": {"stringValue": _SERVICE_NAME},
                        },
                        {
                            "key": "service.version",
                            "value": {"stringValue": _SERVICE_VERSION},
                        },
                    ],
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "tapps_mcp.metrics"},
                        "spans": spans,
                    },
                ],
            },
        ],
    }


def export_to_file(
    metrics: list[ToolCallMetric],
    traces_dir: Path,
) -> Path:
    """Export OTEL trace to a JSON file.

    Args:
        metrics: Tool call metrics to export.
        traces_dir: Directory for trace files.

    Returns:
        Path to the written trace file.
    """
    traces_dir.mkdir(parents=True, exist_ok=True)
    trace_data = export_otel_trace(metrics)

    today = date.today().isoformat()
    path = traces_dir / f"trace_{today}.json"

    try:
        path.write_text(
            json.dumps(trace_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        logger.warning("otel_export_failed", path=str(path), exc_info=True)

    return path
