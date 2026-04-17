"""Backward-compatible re-export.

Imports from :mod:`tapps_brain.contradictions` directly to avoid the
``tapps_core.memory.contradictions`` deprecation chain (EPIC-95.3 / TAP-412).
"""

from __future__ import annotations

from tapps_brain.contradictions import Contradiction as Contradiction
from tapps_brain.contradictions import (
    ContradictionDetector as ContradictionDetector,
)
