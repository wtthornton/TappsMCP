"""Execution metrics collector for MCP tool calls.

Tracks every MCP tool invocation with timing, status, and outcome data.
Records are stored both in-memory (last N calls) and on disk as daily JSONL files.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# In-memory buffer size
_BUFFER_SIZE = 100

# Default retention days
_DEFAULT_RETENTION_DAYS = 90


@dataclass
class ToolCallMetric:
    """Record of a single MCP tool invocation."""

    call_id: str
    tool_name: str
    status: str  # success, failed, timeout, degraded
    duration_ms: float
    started_at: str  # ISO format
    completed_at: str  # ISO format
    file_path: str | None = None
    gate_passed: bool | None = None
    score: float | None = None
    error_code: str | None = None
    degraded: bool = False
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolCallMetric:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ToolCallSummary:
    """Aggregated summary for a set of tool calls."""

    total_calls: int = 0
    success_count: int = 0
    failed_count: int = 0
    timeout_count: int = 0
    degraded_count: int = 0
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    gate_pass_rate: float | None = None
    avg_score: float | None = None


@dataclass
class ToolBreakdown:
    """Per-tool metric breakdown."""

    tool_name: str
    call_count: int = 0
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    gate_pass_rate: float | None = None
    avg_score: float | None = None


class ToolCallMetricsCollector:
    """Collects and queries MCP tool call metrics.

    Thread-safe with internal lock for concurrent recording.
    """

    def __init__(self, metrics_dir: Path) -> None:
        self._metrics_dir = metrics_dir
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._buffer: deque[ToolCallMetric] = deque(maxlen=_BUFFER_SIZE)
        self._write_lock = threading.Lock()

    def record_call(self, metric: ToolCallMetric) -> None:
        """Record a tool call metric to buffer and disk."""
        with self._write_lock:
            self._buffer.append(metric)
            self._append_to_file(metric)

    def record(
        self,
        tool_name: str,
        started_at: datetime,
        completed_at: datetime,
        status: str = "success",
        file_path: str | None = None,
        gate_passed: bool | None = None,
        score: float | None = None,
        error_code: str | None = None,
        degraded: bool = False,
        session_id: str = "",
    ) -> ToolCallMetric:
        """Convenience method to build and record a metric."""
        duration_ms = (completed_at - started_at).total_seconds() * 1000.0
        metric = ToolCallMetric(
            call_id=uuid.uuid4().hex[:16],
            tool_name=tool_name,
            status=status,
            duration_ms=round(duration_ms, 2),
            started_at=started_at.isoformat(),
            completed_at=completed_at.isoformat(),
            file_path=file_path,
            gate_passed=gate_passed,
            score=score,
            error_code=error_code,
            degraded=degraded,
            session_id=session_id,
        )
        self.record_call(metric)
        return metric

    def get_metrics(
        self,
        tool_name: str | None = None,
        status: str | None = None,
        session_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[ToolCallMetric]:
        """Query metrics with optional filters."""
        metrics = self._load_from_disk(since=since, until=until)
        return self._apply_filters(metrics, tool_name, status, session_id)

    def get_recent(self, limit: int = 50) -> list[ToolCallMetric]:
        """Get most recent metrics from the in-memory buffer."""
        with self._write_lock:
            items = list(self._buffer)
        return items[-limit:]

    def get_recent_from_disk(self, limit: int = 500) -> list[ToolCallMetric]:
        """Get most recent metrics from disk (JSONL files).

        Use this for coverage aggregation so metrics are correct even when
        the in-memory buffer is empty (e.g. after server restart).
        """
        metrics = self._load_from_disk(since=None, until=None)
        # Sort by started_at descending (most recent first)
        sorted_metrics = sorted(
            metrics,
            key=lambda m: m.started_at,
            reverse=True,
        )
        return sorted_metrics[:limit]

    def get_summary(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> ToolCallSummary:
        """Get aggregate summary of tool calls."""
        metrics = self._load_from_disk(since=since, until=until)
        return self._compute_summary(metrics)

    def get_summary_by_tool(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[ToolBreakdown]:
        """Get per-tool metric breakdown."""
        metrics = self._load_from_disk(since=since, until=until)

        # Group by tool_name
        by_tool: dict[str, list[ToolCallMetric]] = {}
        for m in metrics:
            by_tool.setdefault(m.tool_name, []).append(m)

        breakdowns: list[ToolBreakdown] = []
        for name, tool_metrics in sorted(by_tool.items()):
            summary = self._compute_summary(tool_metrics)
            breakdowns.append(
                ToolBreakdown(
                    tool_name=name,
                    call_count=summary.total_calls,
                    success_rate=summary.success_rate,
                    avg_duration_ms=summary.avg_duration_ms,
                    p95_duration_ms=summary.p95_duration_ms,
                    gate_pass_rate=summary.gate_pass_rate,
                    avg_score=summary.avg_score,
                )
            )
        return breakdowns

    def cleanup_old_metrics(self, days_to_keep: int = _DEFAULT_RETENTION_DAYS) -> int:
        """Remove JSONL files older than *days_to_keep*."""
        cutoff = date.today() - timedelta(days=days_to_keep)
        removed = 0
        for f in self._metrics_dir.glob("tool_calls_*.jsonl"):
            # Extract date from filename
            try:
                file_date_str = f.stem.replace("tool_calls_", "")
                file_date = date.fromisoformat(file_date_str)
                if file_date < cutoff:
                    f.unlink()
                    removed += 1
            except (ValueError, OSError):
                pass
        return removed

    # -- Private helpers --

    def _append_to_file(self, metric: ToolCallMetric) -> None:
        """Append a metric record to the daily JSONL file."""
        today = date.today().isoformat()
        path = self._metrics_dir / f"tool_calls_{today}.jsonl"
        line = json.dumps(metric.to_dict(), ensure_ascii=False)
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            logger.warning("metric_write_failed", file=str(path), exc_info=True)

    def _load_from_disk(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[ToolCallMetric]:
        """Load metrics from daily JSONL files."""
        metrics: list[ToolCallMetric] = []

        for f in sorted(self._metrics_dir.glob("tool_calls_*.jsonl")):
            # Optionally skip files outside date range
            try:
                file_date_str = f.stem.replace("tool_calls_", "")
                file_date = date.fromisoformat(file_date_str)
                if since and file_date < since.date():
                    continue
                if until and file_date > until.date():
                    continue
            except ValueError:
                continue

            try:
                text = f.read_text(encoding="utf-8")
            except OSError:
                continue

            for line in text.strip().splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict):
                        continue
                    metric = ToolCallMetric.from_dict(data)
                    # Apply time filters at record level
                    if since or until:
                        try:
                            ts = datetime.fromisoformat(metric.started_at)
                            if since and ts < since:
                                continue
                            if until and ts > until:
                                continue
                        except (ValueError, TypeError):
                            pass
                    metrics.append(metric)
                except (json.JSONDecodeError, TypeError):
                    pass

        return metrics

    @staticmethod
    def _apply_filters(
        metrics: list[ToolCallMetric],
        tool_name: str | None,
        status: str | None,
        session_id: str | None,
    ) -> list[ToolCallMetric]:
        """Apply optional filters to a list of metrics."""
        result = metrics
        if tool_name:
            result = [m for m in result if m.tool_name == tool_name]
        if status:
            result = [m for m in result if m.status == status]
        if session_id:
            result = [m for m in result if m.session_id == session_id]
        return result

    @staticmethod
    def _compute_summary(metrics: list[ToolCallMetric]) -> ToolCallSummary:
        """Compute aggregate summary from a list of metrics."""
        if not metrics:
            return ToolCallSummary()

        total = len(metrics)
        success = sum(1 for m in metrics if m.status == "success")
        failed = sum(1 for m in metrics if m.status == "failed")
        timeout = sum(1 for m in metrics if m.status == "timeout")
        degraded = sum(1 for m in metrics if m.degraded)

        durations = [m.duration_ms for m in metrics]
        avg_dur = sum(durations) / len(durations)
        sorted_dur = sorted(durations)
        p95_idx = max(0, int(len(sorted_dur) * 0.95) - 1)
        p95_dur = sorted_dur[p95_idx]

        # Gate pass rate (only for tools that have gate_passed set)
        gate_metrics = [m for m in metrics if m.gate_passed is not None]
        gate_pass_rate: float | None = None
        if gate_metrics:
            gate_pass_rate = sum(1 for m in gate_metrics if m.gate_passed) / len(gate_metrics)

        # Average score (only for tools that have score set)
        score_metrics = [m for m in metrics if m.score is not None]
        avg_score: float | None = None
        if score_metrics:
            avg_score = sum(m.score for m in score_metrics if m.score is not None) / len(
                score_metrics
            )

        return ToolCallSummary(
            total_calls=total,
            success_count=success,
            failed_count=failed,
            timeout_count=timeout,
            degraded_count=degraded,
            success_rate=round(success / total, 4) if total else 0.0,
            avg_duration_ms=round(avg_dur, 2),
            p95_duration_ms=round(p95_dur, 2),
            gate_pass_rate=round(gate_pass_rate, 4) if gate_pass_rate is not None else None,
            avg_score=round(avg_score, 2) if avg_score is not None else None,
        )
