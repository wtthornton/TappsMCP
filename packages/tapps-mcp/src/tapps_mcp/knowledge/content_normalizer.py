"""Backward-compatible re-export."""
from __future__ import annotations

from tapps_core.knowledge.content_normalizer import CodeSnippet as CodeSnippet
from tapps_core.knowledge.content_normalizer import (
    NormalizationResult as NormalizationResult,
)
from tapps_core.knowledge.content_normalizer import ReferenceCard as ReferenceCard
from tapps_core.knowledge.content_normalizer import (
    apply_token_budget as apply_token_budget,
)
from tapps_core.knowledge.content_normalizer import (
    deduplicate_snippets as deduplicate_snippets,
)
from tapps_core.knowledge.content_normalizer import (
    extract_snippets as extract_snippets,
)
from tapps_core.knowledge.content_normalizer import (
    normalize_content as normalize_content,
)
from tapps_core.knowledge.content_normalizer import rank_snippets as rank_snippets
