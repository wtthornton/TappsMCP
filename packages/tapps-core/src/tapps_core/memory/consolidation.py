"""Backward-compatible re-export from tapps-brain."""

from tapps_brain.consolidation import (
    DEFAULT_MIN_ENTRIES_TO_CONSOLIDATE as DEFAULT_MIN_ENTRIES_TO_CONSOLIDATE,
)
from tapps_brain.consolidation import (
    MAX_CONSOLIDATED_VALUE_LENGTH as MAX_CONSOLIDATED_VALUE_LENGTH,
)
from tapps_brain.consolidation import (
    calculate_weighted_confidence as calculate_weighted_confidence,
)
from tapps_brain.consolidation import consolidate as consolidate
from tapps_brain.consolidation import (
    detect_consolidation_reason as detect_consolidation_reason,
)
from tapps_brain.consolidation import (
    generate_consolidated_key as generate_consolidated_key,
)
from tapps_brain.consolidation import merge_tags as merge_tags
from tapps_brain.consolidation import merge_values as merge_values
from tapps_brain.consolidation import select_tier as select_tier
from tapps_brain.consolidation import should_consolidate as should_consolidate
