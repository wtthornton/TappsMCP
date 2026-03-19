"""Verify that tapps_core.memory re-exports all public symbols from tapps_brain.

After the tapps-brain extraction, tapps_core.memory modules are thin shims.
This test ensures the re-export wiring is correct — detailed behavior tests
live in the tapps-brain package (521+ tests).
"""

from __future__ import annotations

import importlib
import types

import pytest


# Each tuple: (tapps_core module path, expected public symbols)
_REEXPORT_MODULES: list[tuple[str, list[str]]] = [
    (
        "tapps_core.memory.bm25",
        ["BM25Scorer", "preprocess", "stem"],
    ),
    (
        "tapps_core.memory.consolidation",
        ["consolidate", "should_consolidate", "merge_values"],
    ),
    (
        "tapps_core.memory.auto_consolidation",
        ["check_consolidation_on_save", "run_periodic_consolidation_scan"],
    ),
    (
        "tapps_core.memory.contradictions",
        ["Contradiction", "ContradictionDetector"],
    ),
    (
        "tapps_core.memory.decay",
        [
            "DecayConfig",
            "calculate_decayed_confidence",
            "get_effective_confidence",
            "is_stale",
        ],
    ),
    (
        "tapps_core.memory.doc_validation",
        ["MemoryDocValidator", "ClaimExtractor", "DocAlignment"],
    ),
    (
        "tapps_core.memory.embeddings",
        ["EmbeddingProvider", "NoopProvider", "get_embedding_provider"],
    ),
    (
        "tapps_core.memory.extraction",
        ["extract_durable_facts"],
    ),
    (
        "tapps_core.memory.federation",
        ["FederatedSearchResult", "federated_search", "FederationConfig"],
    ),
    (
        "tapps_core.memory.fusion",
        ["reciprocal_rank_fusion"],
    ),
    (
        "tapps_core.memory.gc",
        ["MemoryGarbageCollector", "GCResult"],
    ),
    (
        "tapps_core.memory.io",
        ["export_memories", "import_memories"],
    ),
    (
        "tapps_core.memory.models",
        ["MemoryEntry", "MemoryTier", "MemorySource", "MemoryScope"],
    ),
    (
        "tapps_core.memory.persistence",
        ["MemoryPersistence"],
    ),
    (
        "tapps_core.memory.reinforcement",
        ["reinforce"],
    ),
    (
        "tapps_core.memory.relations",
        ["extract_relations", "expand_via_relations"],
    ),
    (
        "tapps_core.memory.reranker",
        ["NoopReranker", "get_reranker"],
    ),
    (
        "tapps_core.memory.retrieval",
        ["MemoryRetriever"],
    ),
    (
        "tapps_core.memory.seeding",
        ["seed_from_profile"],
    ),
    (
        "tapps_core.memory.session_index",
        ["index_session", "search_session_index"],
    ),
    (
        "tapps_core.memory.similarity",
        ["compute_similarity", "find_similar", "is_same_topic"],
    ),
    (
        "tapps_core.memory.store",
        ["MemoryStore"],
    ),
]


@pytest.mark.parametrize(
    ("module_path", "symbols"),
    _REEXPORT_MODULES,
    ids=[m for m, _ in _REEXPORT_MODULES],
)
def test_reexport_symbols_exist(module_path: str, symbols: list[str]) -> None:
    """Each re-exported symbol must be importable from the tapps_core shim."""
    mod = importlib.import_module(module_path)
    for sym in symbols:
        obj = getattr(mod, sym, None)
        assert obj is not None, f"{module_path}.{sym} is missing"


@pytest.mark.parametrize(
    ("module_path", "symbols"),
    _REEXPORT_MODULES,
    ids=[m for m, _ in _REEXPORT_MODULES],
)
def test_reexport_identity(module_path: str, symbols: list[str]) -> None:
    """Re-exported symbols must be the same objects as tapps_brain originals."""
    core_mod = importlib.import_module(module_path)
    brain_path = module_path.replace("tapps_core.memory", "tapps_brain")
    try:
        brain_mod = importlib.import_module(brain_path)
    except ModuleNotFoundError:
        pytest.skip(f"{brain_path} not installed")
    for sym in symbols:
        core_obj = getattr(core_mod, sym, None)
        brain_obj = getattr(brain_mod, sym, None)
        if brain_obj is not None and core_obj is not None:
            if isinstance(core_obj, types.ModuleType):
                assert core_obj.__name__ == brain_obj.__name__
            else:
                assert core_obj is brain_obj, (
                    f"{module_path}.{sym} is not the same object as {brain_path}.{sym}"
                )
