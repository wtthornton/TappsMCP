"""Expert observability system.

Correlates consultation, RAG, and confidence metrics to identify
weak expert areas and generate improvement proposals.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path  # noqa: TC003
from typing import Any

import structlog

from tapps_core.metrics.confidence_metrics import ConfidenceMetricsTracker
from tapps_core.metrics.expert_metrics import ExpertPerformanceTracker
from tapps_core.metrics.rag_metrics import RAGMetricsTracker

logger = structlog.get_logger(__name__)

_WEAK_CONFIDENCE_THRESHOLD = 0.5
_WEAK_SIMILARITY_THRESHOLD = 0.3


@dataclass
class WeakArea:
    """An identified area of weakness in the expert system."""

    domain: str
    weakness_type: str  # low_confidence, low_rag_quality, low_coverage
    severity: str  # info, warning, critical
    details: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImprovementProposal:
    """A suggested improvement for the knowledge base."""

    domain: str
    proposal_type: str  # add_knowledge, update_knowledge, add_examples
    description: str
    priority: str = "medium"  # low, medium, high
    related_weak_area: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ObservabilitySystem:
    """Correlates metrics to identify weak areas and generate improvement proposals."""

    def __init__(
        self,
        metrics_dir: Path,
        expert_tracker: ExpertPerformanceTracker | None = None,
        confidence_tracker: ConfidenceMetricsTracker | None = None,
        rag_tracker: RAGMetricsTracker | None = None,
    ) -> None:
        self._metrics_dir = metrics_dir
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._expert_tracker = expert_tracker or ExpertPerformanceTracker(metrics_dir)
        self._confidence_tracker = confidence_tracker or ConfidenceMetricsTracker(metrics_dir)
        self._rag_tracker = rag_tracker or RAGMetricsTracker(metrics_dir)

    def identify_weak_areas(
        self,
        confidence_threshold: float = _WEAK_CONFIDENCE_THRESHOLD,
        similarity_threshold: float = _WEAK_SIMILARITY_THRESHOLD,
    ) -> list[WeakArea]:
        """Identify domains with quality issues."""
        weak_areas: list[WeakArea] = []

        # Check confidence metrics
        conf_stats = self._confidence_tracker.get_statistics()
        for domain, stats in conf_stats.by_domain.items():
            avg_conf = stats.get("avg_confidence", 0.0)
            if avg_conf < confidence_threshold:
                severity = "critical" if avg_conf < confidence_threshold * 0.5 else "warning"
                weak_areas.append(
                    WeakArea(
                        domain=domain,
                        weakness_type="low_confidence",
                        severity=severity,
                        details=(
                            f"Average confidence {avg_conf:.2f} "
                            f"below threshold {confidence_threshold:.2f}"
                        ),
                        metric_value=avg_conf,
                        threshold=confidence_threshold,
                    )
                )

        # Check RAG metrics
        rag_metrics = self._rag_tracker.get_metrics()
        for domain, stats in rag_metrics.by_domain.items():
            # Low cache hit rate
            hit_rate = stats.get("cache_hit_rate", 0.0)
            if isinstance(hit_rate, (int, float)) and hit_rate < 0.3:
                weak_areas.append(
                    WeakArea(
                        domain=domain,
                        weakness_type="low_rag_quality",
                        severity="warning",
                        details=f"Low RAG cache hit rate: {hit_rate:.2%}",
                        metric_value=hit_rate,
                        threshold=0.3,
                    )
                )

        # Save results
        self._save_weak_areas(weak_areas)
        return weak_areas

    def generate_improvement_proposals(self) -> list[ImprovementProposal]:
        """Generate improvement proposals based on identified weak areas."""
        weak_areas = self.identify_weak_areas()
        proposals: list[ImprovementProposal] = []

        for area in weak_areas:
            if area.weakness_type == "low_confidence":
                proposals.append(
                    ImprovementProposal(
                        domain=area.domain,
                        proposal_type="add_knowledge",
                        description=(
                            f"Add more knowledge files for '{area.domain}' domain. "
                            f"Current avg confidence is {area.metric_value:.2f}."
                        ),
                        priority="high" if area.severity == "critical" else "medium",
                        related_weak_area=area.weakness_type,
                    )
                )
            elif area.weakness_type == "low_rag_quality":
                proposals.append(
                    ImprovementProposal(
                        domain=area.domain,
                        proposal_type="update_knowledge",
                        description=(
                            f"Improve RAG quality for '{area.domain}' domain. "
                            f"Cache hit rate is {area.metric_value:.2%}."
                        ),
                        priority="medium",
                        related_weak_area=area.weakness_type,
                    )
                )

        self._save_proposals(proposals)
        return proposals

    def _save_weak_areas(self, areas: list[WeakArea]) -> None:
        path = self._metrics_dir / "weak_areas.json"
        try:
            path.write_text(
                json.dumps([a.to_dict() for a in areas], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("weak_areas_save_failed", exc_info=True)

    def _save_proposals(self, proposals: list[ImprovementProposal]) -> None:
        path = self._metrics_dir / "improvement_proposals.json"
        try:
            path.write_text(
                json.dumps([p.to_dict() for p in proposals], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("proposals_save_failed", exc_info=True)
