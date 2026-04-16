"""Unit tests for optional reranker (Epic 65.9).

tapps-brain v3 replaced CohereReranker with FlashRankReranker.
``get_reranker`` now accepts ``(enabled, model=None)`` — provider/api_key removed.
Run with: ``pytest -m optional_deps`` to include these tests.
"""

from __future__ import annotations

import pytest

from tapps_core.memory.reranker import (
    RERANKER_TOP_CANDIDATES,
    NoopReranker,
    get_reranker,
)

pytestmark = pytest.mark.optional_deps


# ---------------------------------------------------------------------------
# NoopReranker
# ---------------------------------------------------------------------------


class TestNoopReranker:
    def test_empty_candidates(self) -> None:
        reranker = NoopReranker()
        result = reranker.rerank("query", [], top_k=5)
        assert result == []

    def test_passthrough_order(self) -> None:
        reranker = NoopReranker()
        candidates = [
            ("key-a", "value a"),
            ("key-b", "value b"),
            ("key-c", "value c"),
        ]
        result = reranker.rerank("query", candidates, top_k=3)
        assert [r[0] for r in result] == ["key-a", "key-b", "key-c"]
        assert all(isinstance(r[1], float) for r in result)

    def test_top_k_limits_results(self) -> None:
        reranker = NoopReranker()
        candidates = [
            ("key-1", "v1"),
            ("key-2", "v2"),
            ("key-3", "v3"),
            ("key-4", "v4"),
        ]
        result = reranker.rerank("query", candidates, top_k=2)
        assert len(result) == 2
        assert [r[0] for r in result] == ["key-1", "key-2"]

    def test_scores_decrease_with_position(self) -> None:
        reranker = NoopReranker()
        candidates = [("k1", "v1"), ("k2", "v2"), ("k3", "v3")]
        result = reranker.rerank("query", candidates, top_k=3)
        scores = [r[1] for r in result]
        assert scores[0] > scores[1] > scores[2]


# ---------------------------------------------------------------------------
# get_reranker (v3 API: enabled + optional model; no provider/api_key)
# ---------------------------------------------------------------------------


class TestGetReranker:
    def test_disabled_returns_noop(self) -> None:
        # tapps-brain v3: provider/api_key args removed.
        r = get_reranker(enabled=False)
        assert isinstance(r, NoopReranker)

    def test_enabled_without_flashrank_returns_noop(self) -> None:
        """When flashrank is not installed, get_reranker falls back to NoopReranker."""
        try:
            import flashrank  # type: ignore[import-untyped]  # noqa: F401

            pytest.skip("flashrank is installed — fallback path not exercised")
        except ImportError:
            pass
        r = get_reranker(enabled=True)
        assert isinstance(r, NoopReranker)

    def test_enabled_with_flashrank_returns_flashrank(self) -> None:
        """When flashrank is available, get_reranker returns FlashRankReranker."""
        try:
            import flashrank  # type: ignore[import-untyped]  # noqa: F401
        except ImportError:
            pytest.skip("flashrank not installed")
        from tapps_core.memory.reranker import FlashRankReranker

        r = get_reranker(enabled=True)
        assert isinstance(r, FlashRankReranker)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_reranker_top_candidates_constant() -> None:
    assert RERANKER_TOP_CANDIDATES == 20
