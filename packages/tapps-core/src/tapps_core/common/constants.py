"""Shared constants used across Tapps platform modules.

Centralised here to break circular dependencies between packages
(e.g. ``common.nudges`` needing thresholds that were previously
defined in ``experts.models``).
"""

from __future__ import annotations

# Threshold below which we surface a low-confidence nudge to the AI
LOW_CONFIDENCE_THRESHOLD: float = 0.5

# Threshold above which expert guidance is considered high-confidence
HIGH_CONFIDENCE_THRESHOLD: float = 0.7
