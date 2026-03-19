"""Backward-compatible re-export from tapps-brain."""

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
