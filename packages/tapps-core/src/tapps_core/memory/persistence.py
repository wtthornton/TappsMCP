"""Backward-compatible re-export from tapps-brain.

In tapps-brain >= 3.0 (ADR-007) the SQLite-backed ``MemoryPersistence`` class
was removed.  The primary store interface is now :class:`tapps_brain.store.MemoryStore`.

``MemoryPersistence`` is re-exported here as an alias for ``MemoryStore`` so
that call sites using the legacy name continue to work at the type level.
``_MAX_AUDIT_LINES`` and ``_SCHEMA_VERSION`` were internal SQLite schema
constants; they are stubbed with their last known values for backward compat.
"""

from __future__ import annotations

try:
    from tapps_brain.persistence import _MAX_AUDIT_LINES as _MAX_AUDIT_LINES
    from tapps_brain.persistence import _SCHEMA_VERSION as _SCHEMA_VERSION
    from tapps_brain.persistence import MemoryPersistence as MemoryPersistence
except ImportError:
    # tapps-brain >= 3.0: persistence module removed (ADR-007).
    # Alias MemoryStore as MemoryPersistence; stub the private schema constants.
    from tapps_brain.store import MemoryStore as MemoryPersistence  # noqa: F401

    _MAX_AUDIT_LINES = 1000
    _SCHEMA_VERSION = 17
