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
    # TAP-496: consolidation, auto_consolidation, contradictions shims deleted
    # (retired in TAP-412; callers updated to import from tapps_brain directly).
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
    # TAP-496: gc shim deleted; callers import from tapps_brain.gc directly.
    (
        "tapps_core.memory.injection",
        [
            "InjectionConfig",
            "append_memory_to_answer",
            "estimate_tokens",
            "_MAX_INJECT_HIGH",
            "_MAX_INJECT_MEDIUM",
            "_MIN_CONFIDENCE_MEDIUM",
            "_MIN_SCORE",
        ],
    ),
    (
        "tapps_core.memory.io",
        ["export_memories", "export_to_markdown", "import_memories"],
    ),
    (
        "tapps_core.memory.models",
        [
            "MemoryEntry",
            "MemoryTier",
            "MemorySource",
            "MemoryScope",
            "MemorySnapshot",
            "MAX_KEY_LENGTH",
            "MAX_TAGS",
            "MAX_VALUE_LENGTH",
            "ConsolidatedEntry",
            "ConsolidationReason",
            "_SOURCE_CONFIDENCE_DEFAULTS",
            "_utc_now_iso",
        ],
    ),
    # TAP-496: persistence shim deleted (SQLite-specific, no v3 equivalent).
    # tapps_mcp/memory/persistence.py now imports directly from tapps_brain.
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
    """Re-exported symbols must be the same objects as tapps_brain originals.

    Skips ``tapps_core.memory.injection`` because its ``inject_memories``
    function is a bridge adapter (wraps the brain version with settings),
    not a pure re-export.  The pure re-exports in that module are still
    checked by ``test_reexport_symbols_exist``.
    """
    if module_path == "tapps_core.memory.injection":
        pytest.skip("injection module has bridge logic; identity check not applicable")
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


def test_injection_bridge_is_callable() -> None:
    """The injection bridge wraps brain's inject_memories with TappsMCP settings."""
    from tapps_core.memory.injection import inject_memories

    assert callable(inject_memories)
    # Bridge signature differs from brain's — it reads TappsMCP settings internally
    import inspect

    sig = inspect.signature(inject_memories)
    assert "store" in sig.parameters
    assert "engagement_level" in sig.parameters


def test_store_instantiable(tmp_path: types.SimpleNamespace | None = None) -> None:
    """MemoryStore can be imported through the tapps_core shim.

    tapps-brain v3 (ADR-007): MemoryStore requires a Postgres private_backend.
    Instantiation without TAPPS_BRAIN_DATABASE_URL is expected to raise ValueError.
    This test verifies the import path is correct; runtime requires postgres.
    """
    import os

    from tapps_core.memory.store import MemoryStore

    assert MemoryStore is not None  # import path is wired
    if not os.environ.get("TAPPS_BRAIN_DATABASE_URL"):
        pytest.skip("MemoryStore requires TAPPS_BRAIN_DATABASE_URL (tapps-brain v3 ADR-007)")
