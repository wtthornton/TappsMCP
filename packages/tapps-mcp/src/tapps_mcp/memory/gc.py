"""Backward-compatible re-export.

Imports from :mod:`tapps_brain.gc` directly to avoid the
``tapps_core.memory.gc`` deprecation chain (EPIC-95.3 / TAP-412).
"""

from __future__ import annotations

from tapps_brain.gc import GCResult as GCResult
from tapps_brain.gc import MemoryGarbageCollector as MemoryGarbageCollector
