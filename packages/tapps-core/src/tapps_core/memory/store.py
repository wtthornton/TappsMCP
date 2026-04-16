"""Backward-compatible re-export from tapps-brain.

tapps-brain >= a3654693 renamed ``_MAX_ENTRIES`` to ``_MAX_ENTRIES_DEFAULT``
and added ``_max_entries_from_env()``. This shim re-exports the default
under the old name to preserve the tapps-core public surface.
"""

from tapps_brain.store import _MAX_ENTRIES_DEFAULT
from tapps_brain.store import ConsolidationConfig as ConsolidationConfig
from tapps_brain.store import MemoryStore as MemoryStore
from tapps_brain.store import _scope_rank as _scope_rank
from tapps_brain.store import _validate_write_rules as _validate_write_rules

# Old name preserved for backward compatibility with tapps-core/tapps-mcp consumers.
_MAX_ENTRIES = _MAX_ENTRIES_DEFAULT
