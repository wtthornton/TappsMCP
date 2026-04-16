"""Backward-compatible re-export from tapps-brain.

.. deprecated:: EPIC-95.3 (TAP-412)
    Import from :mod:`tapps_brain.gc` directly. tapps-mcp now delegates GC
    operations to :class:`tapps_core.brain_bridge.BrainBridge`; this shim
    will be removed in TAP-496 (EPIC-95.8).
"""

from __future__ import annotations

import warnings

from tapps_brain.gc import GCResult as GCResult
from tapps_brain.gc import MemoryGarbageCollector as MemoryGarbageCollector

warnings.warn(
    "tapps_core.memory.gc is deprecated; import from tapps_brain.gc directly "
    "or use tapps_core.brain_bridge.BrainBridge.gc(). Removed in EPIC-95.8.",
    DeprecationWarning,
    stacklevel=2,
)
