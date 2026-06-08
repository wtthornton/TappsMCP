"""Best-effort brain KG events for metrics collectors (TAP-1997 phase-1).

Dual-write: local JSON/JSONL metrics remain the read path until brain event
payload reads land (see ``docs/handoff/BRAIN-wave2-capabilities.md``). This
module adds fire-and-forget ``quality_metric`` events without blocking callers.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from tapps_core.metrics.execution_metrics import ToolCallMetric

logger = structlog.get_logger(__name__)


def emit_quality_metric_event(metric: ToolCallMetric) -> None:
    """Emit a ``quality_metric`` brain event for a recorded tool call (best-effort)."""

    async def _emit() -> None:
        try:
            from tapps_core.brain_bridge import create_brain_bridge
            from tapps_core.config.settings import load_settings

            bridge = create_brain_bridge(load_settings())
            if bridge is None or not hasattr(bridge, "record_kg_event"):
                return

            entities: list[dict[str, str]] = [
                {"type": "tool", "id": metric.tool_name},
            ]
            edges: list[dict[str, str]] = []
            if metric.file_path and metric.score is not None:
                file_id = metric.file_path
                score_id = f"{metric.score:.1f}"
                entities.append({"type": "file", "id": file_id})
                edges.append(
                    {"src": file_id, "predicate": "scored", "dst": score_id},
                )

            payload_data: dict[str, Any] = {
                "call_id": metric.call_id,
                "status": metric.status,
                "duration_ms": metric.duration_ms,
                "gate_passed": metric.gate_passed,
                "score": metric.score,
                "degraded": metric.degraded,
                "session_id": metric.session_id,
            }
            if metric.error_code:
                payload_data["error_code"] = metric.error_code

            await bridge.record_kg_event(  # type: ignore[union-attr]
                event_type="quality_metric",
                entities=entities,
                edges=edges,
                payload_data=payload_data,
            )
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
