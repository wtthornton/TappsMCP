"""Protocol interfaces for metrics tracking.

These protocols define the contracts consumed by adaptive scoring and expert
adaptation engines.  Epic 7 (Metrics & Dashboard) will provide richer
implementations; for now, :mod:`tapps_core.adaptive.persistence` supplies
simple file-based concrete classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from tapps_core.adaptive.models import CodeOutcome, ExpertPerformance


class OutcomeTrackerProtocol(Protocol):
    """Structural protocol for outcome tracking."""

    def save_outcome(self, outcome: CodeOutcome) -> None:
        """Persist a single :class:`CodeOutcome`."""
        ...

    def load_outcomes(
        self,
        limit: int | None = None,
        workflow_id: str | None = None,
    ) -> list[CodeOutcome]:
        """Load stored outcomes, optionally filtered."""
        ...

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate statistics over all stored outcomes."""
        ...


class PerformanceTrackerProtocol(Protocol):
    """Structural protocol for expert performance tracking."""

    def track_consultation(
        self,
        expert_id: str,
        domain: str,
        confidence: float,
        query: str | None = None,
    ) -> None:
        """Record a single expert consultation."""
        ...

    def calculate_performance(
        self,
        expert_id: str,
        days: int = 30,
    ) -> ExpertPerformance | None:
        """Calculate aggregated performance for *expert_id* over *days*."""
        ...

    def get_all_performance(
        self,
        days: int = 30,
    ) -> dict[str, ExpertPerformance]:
        """Calculate performance for every tracked expert."""
        ...
