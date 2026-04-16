"""Backward-compatible re-export from tapps-brain.

.. deprecated:: EPIC-95.3 (TAP-412)
    Import from :mod:`tapps_brain.contradictions` directly, or use
    :meth:`tapps_core.brain_bridge.BrainBridge.detect_conflicts`. Removed in
    TAP-496.
"""

from __future__ import annotations

import warnings

from tapps_brain.contradictions import Contradiction as Contradiction
from tapps_brain.contradictions import (
    ContradictionDetector as ContradictionDetector,
)

warnings.warn(
    "tapps_core.memory.contradictions is deprecated; import from "
    "tapps_brain.contradictions directly or use BrainBridge.detect_conflicts(). "
    "Removed in EPIC-95.8.",
    DeprecationWarning,
    stacklevel=2,
)
