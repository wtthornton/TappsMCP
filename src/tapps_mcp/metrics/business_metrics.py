"""Business and aggregate metrics collection.

Tracks adoption, effectiveness, ROI, and operational metrics.
Aggregates from all metric trackers into a unified business view.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import Any

import structlog

from tapps_mcp.metrics.confidence_metrics import ConfidenceMetricsTracker
from tapps_mcp.metrics.execution_metrics import ToolCallMetricsCollector
from tapps_mcp.metrics.expert_metrics import ExpertPerformanceTracker
from tapps_mcp.metrics.outcome_tracker import OutcomeTracker
from tapps_mcp.metrics.rag_metrics import RAGMetricsTracker

logger = structlog.get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class AdoptionMetrics:
    """How much TappsMCP is being used."""

    total_consultations: int = 0
    daily_rate: float = 0.0  # consultations per day
    domain_usage: dict[str, int] = field(default_factory=dict)
    tool_usage: dict[str, int] = field(default_factory=dict)


@dataclass
class EffectivenessMetrics:
    """How effective TappsMCP is at improving quality."""

    avg_score_improvement: float = 0.0  # average before/after delta
    first_pass_success_rate: float = 0.0
    avg_iterations: float = 0.0
    gate_pass_rate: float = 0.0


@dataclass
class QualityMetrics:
    """Expert and RAG quality indicators."""

    avg_confidence: float = 0.0
    confidence_trend: str = "stable"  # improving, stable, degrading
    avg_agreement: float = 0.0
    rag_cache_hit_rate: float = 0.0
    rag_avg_latency_ms: float = 0.0


@dataclass
class ROIMetrics:
    """Return on investment indicators."""

    total_tool_calls: int = 0
    estimated_time_saved_min: float = 0.0  # rough estimate
    avg_call_duration_ms: float = 0.0


@dataclass
class OperationalMetrics:
    """System health and operational indicators."""

    error_rate: float = 0.0
    avg_latency_ms: float = 0.0
    cache_hit_rate: float = 0.0
    degraded_rate: float = 0.0


@dataclass
class BusinessMetricsData:
    """Combined business metrics snapshot."""

    timestamp: str = ""
    adoption: AdoptionMetrics = field(default_factory=AdoptionMetrics)
    effectiveness: EffectivenessMetrics = field(default_factory=EffectivenessMetrics)
    quality: QualityMetrics = field(default_factory=QualityMetrics)
    roi: ROIMetrics = field(default_factory=ROIMetrics)
    operational: OperationalMetrics = field(default_factory=OperationalMetrics)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BusinessMetricsCollector:
    """Aggregates metrics from all trackers into business metrics."""

    def __init__(
        self,
        metrics_dir: Path,
        execution_collector: ToolCallMetricsCollector | None = None,
        outcome_tracker: OutcomeTracker | None = None,
        expert_tracker: ExpertPerformanceTracker | None = None,
        confidence_tracker: ConfidenceMetricsTracker | None = None,
        rag_tracker: RAGMetricsTracker | None = None,
    ) -> None:
        self._metrics_dir = metrics_dir
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._metrics_dir / "business_metrics.json"
        self._write_lock = threading.Lock()

        self._execution = execution_collector or ToolCallMetricsCollector(metrics_dir)
        self._outcomes = outcome_tracker or OutcomeTracker(metrics_dir)
        self._experts = expert_tracker or ExpertPerformanceTracker(metrics_dir)
        self._confidence = confidence_tracker or ConfidenceMetricsTracker(metrics_dir)
        self._rag = rag_tracker or RAGMetricsTracker(metrics_dir)

    def collect(self) -> BusinessMetricsData:
        """Collect current business metrics from all trackers."""
        data = BusinessMetricsData(timestamp=_utc_now().isoformat())

        # Adoption metrics
        data.adoption = self._collect_adoption()

        # Effectiveness metrics
        data.effectiveness = self._collect_effectiveness()

        # Quality metrics
        data.quality = self._collect_quality()

        # ROI metrics
        data.roi = self._collect_roi()

        # Operational metrics
        data.operational = self._collect_operational()

        # Persist snapshot
        self._save(data)

        return data

    def get_latest(self) -> BusinessMetricsData | None:
        """Load the most recent business metrics snapshot."""
        if not self._file.exists():
            return None
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
            return BusinessMetricsData(
                timestamp=raw.get("timestamp", ""),
                adoption=AdoptionMetrics(**raw.get("adoption", {})),
                effectiveness=EffectivenessMetrics(**raw.get("effectiveness", {})),
                quality=QualityMetrics(**raw.get("quality", {})),
                roi=ROIMetrics(**raw.get("roi", {})),
                operational=OperationalMetrics(**raw.get("operational", {})),
            )
        except (json.JSONDecodeError, OSError, TypeError):
            return None

    def _collect_adoption(self) -> AdoptionMetrics:
        exec_summary = self._execution.get_summary()
        tool_breakdown = self._execution.get_summary_by_tool()
        expert_domain = self._experts.get_domain_breakdown()

        tool_usage = {t.tool_name: t.call_count for t in tool_breakdown}
        domain_usage = {d: v.get("consultations", 0) for d, v in expert_domain.items()}

        # Estimate daily rate (total calls / 30 days as rough estimate)
        daily_rate = exec_summary.total_calls / 30.0 if exec_summary.total_calls > 0 else 0.0

        return AdoptionMetrics(
            total_consultations=exec_summary.total_calls,
            daily_rate=round(daily_rate, 2),
            domain_usage=domain_usage,
            tool_usage=tool_usage,
        )

    def _collect_effectiveness(self) -> EffectivenessMetrics:
        outcome_stats = self._outcomes.get_statistics()
        exec_summary = self._execution.get_summary()

        return EffectivenessMetrics(
            first_pass_success_rate=outcome_stats.get("first_pass_success_rate", 0.0),
            avg_iterations=outcome_stats.get("avg_iterations", 0.0),
            gate_pass_rate=exec_summary.gate_pass_rate or 0.0,
        )

    def _collect_quality(self) -> QualityMetrics:
        conf_stats = self._confidence.get_statistics()
        rag_metrics = self._rag.get_metrics()

        return QualityMetrics(
            avg_confidence=conf_stats.avg_confidence,
            avg_agreement=conf_stats.avg_agreement,
            rag_cache_hit_rate=rag_metrics.cache_hit_rate,
            rag_avg_latency_ms=rag_metrics.avg_latency_ms,
        )

    def _collect_roi(self) -> ROIMetrics:
        exec_summary = self._execution.get_summary()

        # Rough estimate: each tool call saves ~2 min of manual work
        estimated_saved = exec_summary.total_calls * 2.0

        return ROIMetrics(
            total_tool_calls=exec_summary.total_calls,
            estimated_time_saved_min=round(estimated_saved, 1),
            avg_call_duration_ms=exec_summary.avg_duration_ms,
        )

    def _collect_operational(self) -> OperationalMetrics:
        exec_summary = self._execution.get_summary()
        rag_metrics = self._rag.get_metrics()

        error_rate = 0.0
        if exec_summary.total_calls > 0:
            error_rate = exec_summary.failed_count / exec_summary.total_calls

        degraded_rate = 0.0
        if exec_summary.total_calls > 0:
            degraded_rate = exec_summary.degraded_count / exec_summary.total_calls

        return OperationalMetrics(
            error_rate=round(error_rate, 4),
            avg_latency_ms=exec_summary.avg_duration_ms,
            cache_hit_rate=rag_metrics.cache_hit_rate,
            degraded_rate=round(degraded_rate, 4),
        )

    def _save(self, data: BusinessMetricsData) -> None:
        with self._write_lock:
            try:
                self._file.write_text(
                    json.dumps(data.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                logger.warning("business_metrics_save_failed", exc_info=True)
