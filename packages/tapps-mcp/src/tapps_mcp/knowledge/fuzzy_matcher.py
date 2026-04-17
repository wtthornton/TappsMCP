"""Backward-compatible re-export."""

from __future__ import annotations

from tapps_core.knowledge.fuzzy_matcher import CONFIDENCE_HIGH as CONFIDENCE_HIGH
from tapps_core.knowledge.fuzzy_matcher import CONFIDENCE_LOW as CONFIDENCE_LOW
from tapps_core.knowledge.fuzzy_matcher import CONFIDENCE_MEDIUM as CONFIDENCE_MEDIUM
from tapps_core.knowledge.fuzzy_matcher import LANGUAGE_HINTS as LANGUAGE_HINTS
from tapps_core.knowledge.fuzzy_matcher import LIBRARY_ALIASES as LIBRARY_ALIASES
from tapps_core.knowledge.fuzzy_matcher import combined_score as combined_score
from tapps_core.knowledge.fuzzy_matcher import confidence_band as confidence_band
from tapps_core.knowledge.fuzzy_matcher import did_you_mean as did_you_mean
from tapps_core.knowledge.fuzzy_matcher import edit_distance as edit_distance
from tapps_core.knowledge.fuzzy_matcher import (
    edit_distance_similarity as edit_distance_similarity,
)
from tapps_core.knowledge.fuzzy_matcher import fuzzy_match_library as fuzzy_match_library
from tapps_core.knowledge.fuzzy_matcher import fuzzy_match_topic as fuzzy_match_topic
from tapps_core.knowledge.fuzzy_matcher import lcs_length as lcs_length
from tapps_core.knowledge.fuzzy_matcher import lcs_similarity as lcs_similarity
from tapps_core.knowledge.fuzzy_matcher import multi_signal_score as multi_signal_score
from tapps_core.knowledge.fuzzy_matcher import resolve_alias as resolve_alias
from tapps_core.knowledge.fuzzy_matcher import token_overlap_score as token_overlap_score
