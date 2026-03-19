"""Shared memory subsystem — re-exports from tapps-brain."""

from tapps_brain.auto_consolidation import (
    ConsolidationResult as ConsolidationResult,
)
from tapps_brain.auto_consolidation import (
    PeriodicScanResult as PeriodicScanResult,
)
from tapps_brain.auto_consolidation import (
    check_consolidation_on_save as check_consolidation_on_save,
)
from tapps_brain.auto_consolidation import (
    run_periodic_consolidation_scan as run_periodic_consolidation_scan,
)
from tapps_brain.consolidation import consolidate as consolidate
from tapps_brain.consolidation import (
    detect_consolidation_reason as detect_consolidation_reason,
)
from tapps_brain.consolidation import should_consolidate as should_consolidate
from tapps_brain.fusion import reciprocal_rank_fusion as reciprocal_rank_fusion
from tapps_brain.models import ConsolidatedEntry as ConsolidatedEntry
from tapps_brain.models import ConsolidationReason as ConsolidationReason
from tapps_brain.relations import RelationEntry as RelationEntry
from tapps_brain.relations import expand_via_relations as expand_via_relations
from tapps_brain.relations import extract_relations as extract_relations
from tapps_brain.relations import (
    extract_relations_from_entries as extract_relations_from_entries,
)
from tapps_brain.similarity import (
    DEFAULT_SIMILARITY_THRESHOLD as DEFAULT_SIMILARITY_THRESHOLD,
)
from tapps_brain.similarity import DEFAULT_TAG_WEIGHT as DEFAULT_TAG_WEIGHT
from tapps_brain.similarity import DEFAULT_TEXT_WEIGHT as DEFAULT_TEXT_WEIGHT
from tapps_brain.similarity import SimilarityResult as SimilarityResult
from tapps_brain.similarity import compute_similarity as compute_similarity
from tapps_brain.similarity import (
    find_consolidation_groups as find_consolidation_groups,
)
from tapps_brain.similarity import find_similar as find_similar
from tapps_brain.similarity import is_same_topic as is_same_topic
