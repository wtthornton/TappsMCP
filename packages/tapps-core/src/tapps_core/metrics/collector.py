"""Central metrics collector singleton.

Provides a lazily-initialized global metrics collector that all
MCP tool handlers use for recording metrics.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from tapps_core.metrics.business_metrics import BusinessMetricsCollector
from tapps_core.metrics.confidence_metrics import ConfidenceMetricsTracker
from tapps_core.metrics.consultation_logger import ConsultationLogger
from tapps_core.metrics.dashboard import DashboardGenerator
from tapps_core.metrics.execution_metrics import ToolCallMetricsCollector
from tapps_core.metrics.expert_metrics import ExpertPerformanceTracker
from tapps_core.metrics.outcome_tracker import OutcomeTracker
from tapps_core.metrics.rag_metrics import RAGMetricsTracker

# Global session ID for this server instance
_SESSION_ID: str = uuid.uuid4().hex[:12]


class MetricsHub:
    """Central hub providing access to all metric trackers.

    Lazily creates sub-trackers on first access.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.session_id = _SESSION_ID
        self._metrics_dir = project_root / ".tapps-mcp" / "metrics"
        self._metrics_dir.mkdir(parents=True, exist_ok=True)

        self.execution = ToolCallMetricsCollector(self._metrics_dir)
        self.outcomes = OutcomeTracker(self._metrics_dir)
        self.experts = ExpertPerformanceTracker(self._metrics_dir)
        self.confidence = ConfidenceMetricsTracker(self._metrics_dir)
        self.rag = RAGMetricsTracker(self._metrics_dir)
        self.consultations = ConsultationLogger(self._metrics_dir)
        self.business = BusinessMetricsCollector(
            self._metrics_dir,
            execution_collector=self.execution,
            outcome_tracker=self.outcomes,
            expert_tracker=self.experts,
            confidence_tracker=self.confidence,
            rag_tracker=self.rag,
        )

    def get_dashboard_generator(
        self,
        memory_store: object | None = None,
    ) -> DashboardGenerator:
        """Create a dashboard generator with all trackers."""
        return DashboardGenerator(
            self._metrics_dir,
            execution_collector=self.execution,
            outcome_tracker=self.outcomes,
            expert_tracker=self.experts,
            confidence_tracker=self.confidence,
            rag_tracker=self.rag,
            business_collector=self.business,
            memory_store=memory_store,  # type: ignore[arg-type]
        )

    @property
    def metrics_dir(self) -> Path:
        return self._metrics_dir


# Singleton instance
_hub: MetricsHub | None = None


def get_metrics_hub() -> MetricsHub:
    """Get or create the global MetricsHub."""
    global _hub
    if _hub is None:
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        _hub = MetricsHub(settings.project_root)
    return _hub


def reset_metrics_hub() -> None:
    """Reset the global hub (for testing)."""
    global _hub
    _hub = None
