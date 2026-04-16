"""Backward-compatible re-export from tapps-brain.

.. deprecated:: EPIC-95.3 (TAP-412)
    Import from :mod:`tapps_brain.auto_consolidation` directly, or use
    :meth:`tapps_core.brain_bridge.BrainBridge.consolidate` which wraps
    ``run_periodic_consolidation_scan``. Removed in TAP-496.
"""

from __future__ import annotations

import warnings

from tapps_brain.auto_consolidation import (
    CONSOLIDATION_STATE_FILE as CONSOLIDATION_STATE_FILE,
)
from tapps_brain.auto_consolidation import (
    ConsolidationResult as ConsolidationResult,
)
from tapps_brain.auto_consolidation import (
    PeriodicScanResult as PeriodicScanResult,
)
from tapps_brain.auto_consolidation import (
    _get_last_scan_time as _get_last_scan_time,
)
from tapps_brain.auto_consolidation import (
    _update_last_scan_time as _update_last_scan_time,
)
from tapps_brain.auto_consolidation import (
    check_consolidation_on_save as check_consolidation_on_save,
)
from tapps_brain.auto_consolidation import (
    run_periodic_consolidation_scan as run_periodic_consolidation_scan,
)
from tapps_brain.auto_consolidation import (
    should_run_auto_consolidation as should_run_auto_consolidation,
)

warnings.warn(
    "tapps_core.memory.auto_consolidation is deprecated; import from "
    "tapps_brain.auto_consolidation directly or use BrainBridge.consolidate(). "
    "Removed in EPIC-95.8.",
    DeprecationWarning,
    stacklevel=2,
)
