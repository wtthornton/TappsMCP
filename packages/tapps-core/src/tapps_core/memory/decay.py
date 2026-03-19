"""Backward-compatible re-export from tapps-brain."""

from tapps_brain.decay import DecayConfig as DecayConfig
from tapps_brain.decay import _days_since as _days_since
from tapps_brain.decay import _decay_reference_time as _decay_reference_time
from tapps_brain.decay import _get_ceiling as _get_ceiling
from tapps_brain.decay import _get_half_life as _get_half_life
from tapps_brain.decay import (
    calculate_decayed_confidence as calculate_decayed_confidence,
)
from tapps_brain.decay import (
    get_effective_confidence as get_effective_confidence,
)
from tapps_brain.decay import is_stale as is_stale
