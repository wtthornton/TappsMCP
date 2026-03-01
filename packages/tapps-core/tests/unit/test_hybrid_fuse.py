"""Unit tests for VectorKnowledgeBase._hybrid_fuse() — hybrid retrieval fusion."""

from __future__ import annotations

import pytest

from tapps_core.experts.models import KnowledgeChunk
from tapps_core.experts.vector_rag import VectorKnowledgeBase


def _chunk(
    content: str = "text",
    source_file: str = "a.md",
    line_start: int = 1,
    line_end: int = 10,
    score: float = 0.8,
) -> KnowledgeChunk:
    """Helper to create a KnowledgeChunk."""
    return KnowledgeChunk(
        content=content,
        source_file=source_file,
        line_start=line_start,
        line_end=line_end,
        score=score,
    )


class TestHybridFuseInputVariations:
    """Empty / single-source fusion scenarios."""

    @pytest.mark.parametrize(
        "vec,kw,expected_len,expected_score",
        [
            ([], [], 0, None),
            ([], [{"source_file": "kw.md", "score": 0.9}], 1, 0.27),  # keyword-only: 0.3*0.9
            ([{"source_file": "vec.md", "score": 0.9}], [], 1, 0.54),  # vector-only: 0.6*0.9
        ],
        ids=["both-empty", "keyword-only", "vector-only"],
    )
    def test_single_source_scoring(self, vec, kw, expected_len, expected_score) -> None:
        v = [_chunk(**c) for c in vec]
        k = [_chunk(**c) for c in kw]
        result = VectorKnowledgeBase._hybrid_fuse(v, k, max_results=5)
        assert len(result) == expected_len
        if expected_score is not None:
            assert abs(result[0].score - expected_score) < 0.01


class TestHybridFuseOverlap:
    """Structural bonus for chunks appearing in both sets."""

    def test_hybrid_structural_bonus(self) -> None:
        """Chunk in both sets: 0.6*0.8 + 0.3*0.7 + 0.1 = 0.79."""
        vec = [_chunk(source_file="shared.md", line_start=1, score=0.8)]
        kw = [_chunk(source_file="shared.md", line_start=1, score=0.7)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert len(result) == 1
        assert abs(result[0].score - 0.79) < 0.01

    def test_no_overlap_all_unique(self) -> None:
        """Disjoint results — no structural bonus."""
        vec = [_chunk(source_file="v1.md", line_start=1, score=0.8)]
        kw = [_chunk(source_file="k1.md", line_start=1, score=0.9)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert len(result) == 2
        scores = sorted([r.score for r in result], reverse=True)
        assert abs(scores[0] - 0.48) < 0.01  # 0.6*0.8
        assert abs(scores[1] - 0.27) < 0.01  # 0.3*0.9

    def test_full_overlap(self) -> None:
        """All chunks in both sets → all get structural bonus > 0.5."""
        vec = [
            _chunk(source_file="a.md", line_start=1, score=0.9),
            _chunk(source_file="b.md", line_start=5, score=0.7),
        ]
        kw = [
            _chunk(source_file="a.md", line_start=1, score=0.8),
            _chunk(source_file="b.md", line_start=5, score=0.6),
        ]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert len(result) == 2
        assert all(r.score > 0.5 for r in result)


class TestHybridFuseDedup:
    """Deduplication by (source_file, line_start) key."""

    def test_same_source_different_line_not_merged(self) -> None:
        vec = [_chunk(source_file="a.md", line_start=1, score=0.9)]
        kw = [_chunk(source_file="a.md", line_start=50, score=0.8)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert len(result) == 2

    def test_keyword_dedup_keeps_highest_score(self) -> None:
        vec = [_chunk(source_file="a.md", line_start=1, score=0.8)]
        kw = [
            _chunk(source_file="b.md", line_start=1, score=0.5),
            _chunk(source_file="b.md", line_start=1, score=0.9),
        ]  # same key, higher
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        kw_result = [r for r in result if r.source_file == "b.md"]
        assert len(kw_result) == 1
        assert abs(kw_result[0].score - 0.27) < 0.01  # 0.3*0.9


class TestHybridFuseScoring:
    """Score calculation, ordering, and clamping."""

    def test_score_clamped_at_one(self) -> None:
        vec = [_chunk(source_file="a.md", line_start=1, score=1.0)]
        kw = [_chunk(source_file="a.md", line_start=1, score=1.0)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert result[0].score <= 1.0

    def test_score_rounded_to_4_decimals(self) -> None:
        vec = [_chunk(source_file="a.md", score=0.333333)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, [], max_results=5)
        score_str = str(result[0].score)
        if "." in score_str:
            assert len(score_str.split(".")[1]) <= 4

    def test_custom_weights(self) -> None:
        vec = [_chunk(source_file="a.md", score=1.0)]
        default = VectorKnowledgeBase._hybrid_fuse(vec, [], max_results=5)
        custom = VectorKnowledgeBase._hybrid_fuse(vec, [], max_results=5, vector_weight=0.9)
        assert custom[0].score > default[0].score

    def test_sorted_by_score_descending(self) -> None:
        vec = [
            _chunk(source_file="low.md", score=0.3),
            _chunk(source_file="high.md", score=0.9),
            _chunk(source_file="mid.md", score=0.6),
        ]
        result = VectorKnowledgeBase._hybrid_fuse(vec, [], max_results=5)
        scores = [r.score for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_content_preserved(self) -> None:
        vec = [_chunk(content="important content", source_file="a.md", score=0.8)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, [], max_results=5)
        assert result[0].content == "important content"

    def test_max_results_limits_output(self) -> None:
        vec = [_chunk(source_file=f"v{i}.md", score=0.8 - i * 0.05) for i in range(5)]
        kw = [_chunk(source_file=f"k{i}.md", score=0.7 - i * 0.05) for i in range(5)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=3)
        assert len(result) == 3


class TestVectorKnowledgeBasePublicAPI:
    """Public methods via simple backend (complements test_vector_rag.py with edge cases)."""

    def test_get_context_respects_max_length(self, tmp_path) -> None:
        content = "\n\n".join(f"## Section {i}\n{'x' * 200}" for i in range(20))
        (tmp_path / "big.md").write_text(content)
        kb = VectorKnowledgeBase(tmp_path)
        ctx = kb.get_context("section", max_length=100)
        assert len(ctx) <= 200  # slack for formatting

    def test_get_sources_deduplicates(self, tmp_path) -> None:
        (tmp_path / "a.md").write_text("# Topic\nKeyword appears here.\n\nKeyword appears again.")
        kb = VectorKnowledgeBase(tmp_path)
        sources = kb.get_sources("keyword")
        assert len(sources) == len(set(sources))
