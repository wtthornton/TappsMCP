"""Backward-compatible re-export.

tapps-brain >= 3.0 (ADR-007) removed the SQLite-backed ``MemoryPersistence``
class. The primary store interface is now :class:`tapps_brain.store.MemoryStore`,
which this shim aliases as ``MemoryPersistence`` for legacy call sites.
"""

from __future__ import annotations

try:
    from tapps_brain.persistence import MemoryPersistence as MemoryPersistence
except ImportError:
    from tapps_brain.store import MemoryStore as MemoryPersistence  # noqa: F401
