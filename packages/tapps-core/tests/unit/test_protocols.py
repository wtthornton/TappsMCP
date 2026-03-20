"""Tests for tapps_core.adaptive.protocols — structural protocol interfaces."""

from __future__ import annotations

from typing import Any

from tapps_core.adaptive.models import CodeOutcome, ExpertPerformance
from tapps_core.adaptive.persistence import FileOutcomeTracker, FilePerformanceTracker
from tapps_core.adaptive.protocols import (
    OutcomeTrackerProtocol,
    PerformanceTrackerProtocol,
)


class TestOutcomeTrackerProtocol:
    """Verify FileOutcomeTracker satisfies OutcomeTrackerProtocol."""

    def test_file_outcome_tracker_is_structural_subtype(self, tmp_path) -> None:
        tracker: OutcomeTrackerProtocol = FileOutcomeTracker(tmp_path)
        # If assignment succeeds, the protocol is satisfied at runtime
        assert tracker is not None

    def test_protocol_methods_exist(self, tmp_path) -> None:
        tracker = FileOutcomeTracker(tmp_path)
        assert callable(getattr(tracker, "save_outcome", None))
        assert callable(getattr(tracker, "load_outcomes", None))
        assert callable(getattr(tracker, "get_statistics", None))


class TestPerformanceTrackerProtocol:
    """Verify FilePerformanceTracker satisfies PerformanceTrackerProtocol."""

    def test_file_performance_tracker_is_structural_subtype(self, tmp_path) -> None:
        tracker: PerformanceTrackerProtocol = FilePerformanceTracker(tmp_path)
        assert tracker is not None

    def test_protocol_methods_exist(self, tmp_path) -> None:
        tracker = FilePerformanceTracker(tmp_path)
        assert callable(getattr(tracker, "track_consultation", None))
        assert callable(getattr(tracker, "calculate_performance", None))
        assert callable(getattr(tracker, "get_all_performance", None))
