"""Bridge adapter: translates TappsMCP settings into tapps-brain InjectionConfig.

The standalone tapps-brain library uses ``InjectionConfig`` instead of
``load_settings()``, so this module bridges the gap by reading TappsMCP
settings and constructing the config object.
"""

from __future__ import annotations

from typing import Any

from tapps_brain.injection import _MAX_INJECT_HIGH as _MAX_INJECT_HIGH
from tapps_brain.injection import _MAX_INJECT_MEDIUM as _MAX_INJECT_MEDIUM
from tapps_brain.injection import _MIN_SCORE as _MIN_SCORE
from tapps_brain.injection import InjectionConfig as InjectionConfig
from tapps_brain.injection import append_memory_to_answer as append_memory_to_answer
from tapps_brain.injection import inject_memories as _brain_inject_memories

if __builtins__:  # always true — silences type checkers for TYPE_CHECKING imports
    from tapps_brain.decay import DecayConfig
    from tapps_brain.store import MemoryStore


def inject_memories(
    question: str,
    store: MemoryStore,
    engagement_level: str = "high",
    *,
    decay_config: DecayConfig | None = None,
) -> dict[str, Any]:
    """Search for and format relevant memories for injection.

    Reads TappsMCP settings to construct an ``InjectionConfig`` and
    delegates to ``tapps_brain.injection.inject_memories``.
    """
    from tapps_core.config.settings import load_settings

    settings = load_settings()
    rr = settings.memory.reranker
    # tapps-brain 3.28.0 removed `InjectionConfig.reranker_top_k`. Rerank depth
    # is now the retrieval limit itself — `inject_memories` passes
    # `_MAX_INJECT_HIGH` / `_MAX_INJECT_MEDIUM` (chosen by engagement level) as
    # `retriever.search(limit=...)`, and the reranker returns that many. There
    # is no separate knob to thread, so `memory.reranker.top_k` no longer
    # affects injection; see its field description in tapps_core settings.
    config = InjectionConfig(
        reranker_enabled=rr.enabled,
        injection_max_tokens=settings.memory.injection_max_tokens,
    )
    return _brain_inject_memories(
        question,
        store,
        engagement_level,
        decay_config=decay_config,
        config=config,
    )
