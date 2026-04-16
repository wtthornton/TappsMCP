"""Backward-compatible re-export from tapps-brain.

In tapps-brain >= 3.0 ``CohereReranker`` was removed and replaced by
``FlashRankReranker``.  ``get_reranker`` no longer accepts ``provider`` or
``api_key`` keyword arguments.
"""

from tapps_brain.reranker import RERANKER_TOP_CANDIDATES as RERANKER_TOP_CANDIDATES
from tapps_brain.reranker import FlashRankReranker as FlashRankReranker
from tapps_brain.reranker import NoopReranker as NoopReranker
from tapps_brain.reranker import Reranker as Reranker
from tapps_brain.reranker import get_reranker as get_reranker

# Backward compat alias — CohereReranker was removed in v3 (replaced by FlashRankReranker).
CohereReranker = FlashRankReranker
