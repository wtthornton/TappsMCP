"""Backward-compatible re-export from tapps-brain."""

from tapps_brain.similarity import (
    DEFAULT_SIMILARITY_THRESHOLD as DEFAULT_SIMILARITY_THRESHOLD,
)
from tapps_brain.similarity import DEFAULT_TAG_WEIGHT as DEFAULT_TAG_WEIGHT
from tapps_brain.similarity import DEFAULT_TEXT_WEIGHT as DEFAULT_TEXT_WEIGHT
from tapps_brain.similarity import SimilarityResult as SimilarityResult
from tapps_brain.similarity import compute_similarity as compute_similarity
from tapps_brain.similarity import cosine_similarity as cosine_similarity
from tapps_brain.similarity import (
    find_consolidation_groups as find_consolidation_groups,
)
from tapps_brain.similarity import find_similar as find_similar
from tapps_brain.similarity import is_same_topic as is_same_topic
from tapps_brain.similarity import jaccard_similarity as jaccard_similarity
from tapps_brain.similarity import same_topic_score as same_topic_score
from tapps_brain.similarity import tag_similarity as tag_similarity
from tapps_brain.similarity import text_similarity as text_similarity
