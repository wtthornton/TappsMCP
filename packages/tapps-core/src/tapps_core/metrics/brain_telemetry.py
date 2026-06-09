"""Best-effort brain telemetry for metrics collectors (TAP-1997).

Phase 1: dual-write KG ``quality_metric`` events + memory entries (readable).
Phase 2 (blocked on ``brain_query_events``): drop local JSONL when
``TAPPS_METRICS_STORAGE=brain`` and read payloads from brain only.

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


def metrics_storage_mode() -> Literal["local", "dual", "brain"]:
    """Return metrics persistence mode (default ``dual``)."""
    raw = os.environ.get(_STORAGE_ENV, "dual").strip().lower()
    if raw in _VALID_STORAGE:
        return raw  # type: ignore[return-value]
    return "dual"


def metric_memory_key(call_id: str) -> str:
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
            if bridge is None:
                return

            if hasattr(bridge, "record_kg_event"):
                await _emit_kg_event(bridge, metric)
            if hasattr(bridge, "save"):
                await _persist_metric_memory(bridge, metric)
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
        event_type="quality_metric",
        entities=entities,
        edges=None,
        payload_data=payload_data,
    )


async def _persist_metric_memory(bridge: Any, metric: ToolCallMetric) -> None:
    """Store the full metric record in brain memory for payload read-back."""
    await bridge.save(
        key=metric_memory_key(metric.call_id),
        value=json.dumps(metric.to_dict(), ensure_ascii=False),
        tier="context",
        scope="project",
        tags=["quality_metric", "metrics"],
        source="agent",
        source_agent="tapps-metrics",
    )


def _parse_metric_entry(entry: dict[str, Any]) -> ToolCallMetric | None:
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


async def load_tool_call_metrics_from_brain(
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 500,
) -> list[ToolCallMetric]:
    """Load tool-call metrics from brain memory (TAP-1997 phase-1.5 read path)."""
    from tapps_core.brain_bridge import create_brain_bridge
    from tapps_core.config.settings import load_settings

    bridge = create_brain_bridge(load_settings())
    if bridge is None or not hasattr(bridge, "search"):
        return []

    try:
        results = await bridge.search(_METRIC_KEY_PREFIX, limit=limit, tier="context")
    except Exception:
        logger.debug("quality_metric_brain_load_failed", exc_info=True)
        return []

    metrics: list[ToolCallMetric] = []
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
