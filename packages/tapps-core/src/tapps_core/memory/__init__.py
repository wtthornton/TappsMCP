"""Shared memory subsystem for persistent cross-session knowledge."""

# Similarity detection (Epic 58, Story 58.1)
from tapps_core.memory.similarity import (
    DEFAULT_SIMILARITY_THRESHOLD as DEFAULT_SIMILARITY_THRESHOLD,
)
from tapps_core.memory.similarity import (
    DEFAULT_TAG_WEIGHT as DEFAULT_TAG_WEIGHT,
)
from tapps_core.memory.similarity import (
    DEFAULT_TEXT_WEIGHT as DEFAULT_TEXT_WEIGHT,
)
from tapps_core.memory.similarity import SimilarityResult as SimilarityResult
from tapps_core.memory.similarity import compute_similarity as compute_similarity
from tapps_core.memory.similarity import (
    find_consolidation_groups as find_consolidation_groups,
)
from tapps_core.memory.similarity import find_similar as find_similar
from tapps_core.memory.similarity import is_same_topic as is_same_topic

# Consolidation engine (Epic 58, Story 58.2)
from tapps_core.memory.consolidation import consolidate as consolidate
from tapps_core.memory.consolidation import (
    detect_consolidation_reason as detect_consolidation_reason,
)
from tapps_core.memory.consolidation import (
    should_consolidate as should_consolidate,
)
from tapps_core.memory.models import ConsolidatedEntry as ConsolidatedEntry
from tapps_core.memory.models import ConsolidationReason as ConsolidationReason

# RRF fusion (Epic 65.8)
from tapps_core.memory.fusion import reciprocal_rank_fusion as reciprocal_rank_fusion

# Auto-consolidation triggers (Epic 58, Story 58.3)
from tapps_core.memory.auto_consolidation import (
    ConsolidationResult as ConsolidationResult,
)
from tapps_core.memory.auto_consolidation import (
    PeriodicScanResult as PeriodicScanResult,
)
from tapps_core.memory.auto_consolidation import (
    check_consolidation_on_save as check_consolidation_on_save,
)
from tapps_core.memory.auto_consolidation import (
    run_periodic_consolidation_scan as run_periodic_consolidation_scan,
)
