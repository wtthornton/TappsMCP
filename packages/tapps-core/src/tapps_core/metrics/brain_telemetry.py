"""Best-effort brain telemetry for metrics collectors (TAP-1997).

Phase 1: dual-write KG ``quality_metric`` events + local JSONL (``dual`` mode).
Phase 2: read payloads via ``brain_query_events``; ``brain`` mode skips JSONL.

See ``docs/handoff/BRAIN-wave2-capabilities.md``.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import structlog

if TYPE_CHECKING:
    from tapps_core.metrics.execution_metrics import ToolCallMetric

from tapps_core.knowledge.kg_keys import entity_spec

logger = structlog.get_logger(__name__)

_METRIC_KEY_PREFIX = "metrics:tool_call:"
_STORAGE_ENV = "TAPPS_METRICS_STORAGE"
_VALID_STORAGE = frozenset({"local", "dual", "brain"})
_QUALITY_METRIC_EVENT = "quality_metric"


def metrics_storage_mode() -> Literal["local", "dual", "brain"]:
    """Return metrics persistence mode (default ``dual``)."""
    raw = os.environ.get(_STORAGE_ENV, "dual").strip().lower()
    if raw in _VALID_STORAGE:
        return raw  # type: ignore[return-value]
    return "dual"


def metric_memory_key(call_id: str) -> str:
    """Legacy memory key prefix (phase-1.5; retained for test compatibility)."""
    return f"{_METRIC_KEY_PREFIX}{call_id}"


def emit_quality_metric_event(metric: ToolCallMetric) -> None:
    """Emit brain telemetry for a recorded tool call (best-effort, non-blocking)."""
    mode = metrics_storage_mode()
    if mode == "local":
        return

    async def _emit() -> None:
        try:
            from tapps_core.brain_bridge import create_brain_bridge
            from tapps_core.config.settings import load_settings

            bridge = create_brain_bridge(load_settings())
            if bridge is None or not hasattr(bridge, "record_kg_event"):
                return
            await _emit_kg_event(bridge, metric)
        except Exception:
            logger.debug("quality_metric_brain_emit_failed", exc_info=True)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    try:
        loop.create_task(_emit())  # noqa: RUF006
    except Exception:
        pass


async def _emit_kg_event(bridge: Any, metric: ToolCallMetric) -> None:
    entities: list[dict[str, str]] = []
    if metric.file_path:
        entities.append(entity_spec("file", metric.file_path))
    entities.append(entity_spec("tool", metric.tool_name))

    payload_data: dict[str, Any] = {
        "call_id": metric.call_id,
        "status": metric.status,
        "duration_ms": metric.duration_ms,
        "gate_passed": metric.gate_passed,
        "score": metric.score,
        "degraded": metric.degraded,
        "session_id": metric.session_id,
        "started_at": metric.started_at,
        "completed_at": metric.completed_at,
        "tool_name": metric.tool_name,
    }
    if metric.file_path:
        payload_data["file_path"] = metric.file_path
        payload_data["subject_key"] = metric.file_path
    if metric.error_code:
        payload_data["error_code"] = metric.error_code

    await bridge.record_kg_event(
        event_type=_QUALITY_METRIC_EVENT,
        entities=entities,
        edges=None,
        payload_data=payload_data,
    )


def _parse_metric_payload(payload: dict[str, Any]) -> ToolCallMetric | None:
    from tapps_core.metrics.execution_metrics import ToolCallMetric

    if not payload.get("call_id") or not payload.get("tool_name"):
        return None
    try:
        return ToolCallMetric.from_dict(payload)
    except (TypeError, KeyError):
        return None


def _parse_metric_entry(entry: dict[str, Any]) -> ToolCallMetric | None:
    """Parse a legacy memory-search entry (phase-1.5 fallback)."""
    from tapps_core.metrics.execution_metrics import ToolCallMetric

    raw = entry.get("value") or entry.get("content") or ""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return ToolCallMetric.from_dict(data)
    except (TypeError, KeyError):
        return None


def _parse_metric_event(event: dict[str, Any]) -> ToolCallMetric | None:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return _parse_metric_payload(payload)
    return None


def _metric_in_window(
    metric: ToolCallMetric,
    since: datetime | None,
    until: datetime | None,
) -> bool:
    if since is None and until is None:
        return True
    try:
        ts = datetime.fromisoformat(metric.started_at)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return True
    if since is not None and ts < since:
        return False
    return not (until is not None and ts > until)


def _iso_or_none(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


async def load_tool_call_metrics_from_brain(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 500,
) -> list[ToolCallMetric]:
    """Load tool-call metrics from ``brain_query_events`` (TAP-1997 phase 2)."""
    from tapps_core.brain_bridge import create_brain_bridge
    from tapps_core.config.settings import load_settings

    bridge = create_brain_bridge(load_settings())
    if bridge is None:
        return []

    metrics: list[ToolCallMetric] = []

    if hasattr(bridge, "query_events"):
        try:
            events = await bridge.query_events(
                _QUALITY_METRIC_EVENT,
                since=_iso_or_none(since),
                until=_iso_or_none(until),
                limit=limit,
            )
        except Exception:
            logger.debug("quality_metric_brain_query_failed", exc_info=True)
            events = []
        for event in events:
            if not isinstance(event, dict):
                continue
            metric = _parse_metric_event(event)
            if metric is None:
                continue
            if _metric_in_window(metric, since, until):
                metrics.append(metric)

    if not metrics and hasattr(bridge, "search"):
        try:
            results = await bridge.search(_METRIC_KEY_PREFIX, limit=limit, tier="context")
        except Exception:
            logger.debug("quality_metric_brain_load_failed", exc_info=True)
            results = []
        for entry in results:
            if not isinstance(entry, dict):
                continue
            metric = _parse_metric_entry(entry)
            if metric is None:
                continue
            if _metric_in_window(metric, since, until):
                metrics.append(metric)

    metrics.sort(key=lambda m: m.started_at, reverse=True)
    return metrics[:limit]


async def hydrate_execution_metrics_from_brain(
    collector: Any,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 500,
) -> int:
    """Merge brain-backed metrics into the collector in-memory buffer."""
    loaded = await load_tool_call_metrics_from_brain(since=since, until=until, limit=limit)
    if not loaded:
        return 0
    with collector._write_lock:
        existing_ids = {m.call_id for m in collector._buffer}
        for metric in loaded:
            if metric.call_id not in existing_ids:
                collector._buffer.append(metric)
                existing_ids.add(metric.call_id)
    return len(loaded)


def sync_hydrate_execution_metrics_from_brain(
    collector: Any,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 500,
) -> int:
    """Sync wrapper for :func:`hydrate_execution_metrics_from_brain`."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            hydrate_execution_metrics_from_brain(
                collector,
                since=since,
                until=until,
                limit=limit,
            )
        )
    return 0
