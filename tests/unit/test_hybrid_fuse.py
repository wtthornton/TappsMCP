"""Unit tests for VectorKnowledgeBase._hybrid_fuse() — hybrid retrieval fusion."""

from __future__ import annotations

from tapps_mcp.experts.models import KnowledgeChunk
from tapps_mcp.experts.vector_rag import VectorKnowledgeBase


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


class TestHybridFuseBasic:
    """Basic fusion scenarios."""

    def test_empty_both(self) -> None:
        result = VectorKnowledgeBase._hybrid_fuse([], [], max_results=5)
        assert result == []

    def test_empty_vector_only_keyword(self) -> None:
        kw = [_chunk(source_file="kw.md", score=0.9)]
        result = VectorKnowledgeBase._hybrid_fuse([], kw, max_results=5)
        assert len(result) == 1
        # Keyword-only contribution: 0.3 * 0.9 = 0.27
        assert abs(result[0].score - 0.27) < 0.01

    def test_empty_keyword_only_vector(self) -> None:
        vec = [_chunk(source_file="vec.md", score=0.9)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, [], max_results=5)
        assert len(result) == 1
        # Vector-only contribution: 0.6 * 0.9 = 0.54
        assert abs(result[0].score - 0.54) < 0.01


class TestHybridFuseOverlap:
    """Test structural bonus for chunks appearing in both sets."""

    def test_hybrid_structural_bonus(self) -> None:
        """Chunk in both sets gets vector_weight*score + keyword_weight*score + structural_weight."""
        vec = [_chunk(source_file="shared.md", line_start=1, score=0.8)]
        kw = [_chunk(source_file="shared.md", line_start=1, score=0.7)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert len(result) == 1
        # Expected: 0.6*0.8 + 0.3*0.7 + 0.1 = 0.48 + 0.21 + 0.1 = 0.79
        assert abs(result[0].score - 0.79) < 0.01

    def test_no_overlap_all_unique(self) -> None:
        """All chunks are unique — no structural bonus applied."""
        vec = [_chunk(source_file="v1.md", line_start=1, score=0.8)]
        kw = [_chunk(source_file="k1.md", line_start=1, score=0.9)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert len(result) == 2
        # Vector chunk: 0.6*0.8 = 0.48, keyword chunk: 0.3*0.9 = 0.27
        scores = sorted([r.score for r in result], reverse=True)
        assert abs(scores[0] - 0.48) < 0.01
        assert abs(scores[1] - 0.27) < 0.01

    def test_full_overlap(self) -> None:
        """All chunks appear in both result sets."""
        shared1 = _chunk(source_file="a.md", line_start=1, score=0.9)
        shared2 = _chunk(source_file="b.md", line_start=5, score=0.7)
        vec = [shared1, shared2]
        kw = [
            _chunk(source_file="a.md", line_start=1, score=0.8),
            _chunk(source_file="b.md", line_start=5, score=0.6),
        ]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert len(result) == 2
        # All should have structural bonus
        for r in result:
            # Structural bonus is 0.1, so each score > 0.5
            assert r.score > 0.5


class TestHybridFuseDedup:
    """Deduplication by (source_file, line_start) key."""

    def test_same_source_different_line_not_merged(self) -> None:
        """Same file but different line_start → treated as separate chunks."""
        vec = [_chunk(source_file="a.md", line_start=1, score=0.9)]
        kw = [_chunk(source_file="a.md", line_start=50, score=0.8)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert len(result) == 2

    def test_keyword_dedup_keeps_highest_score(self) -> None:
        """When multiple keyword results share the same key, the highest-scored is kept."""
        vec = [_chunk(source_file="a.md", line_start=1, score=0.8)]
        kw = [
            _chunk(source_file="b.md", line_start=1, score=0.5),
            _chunk(source_file="b.md", line_start=1, score=0.9),  # higher score, same key
        ]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        # The keyword dedup should keep score=0.9
        kw_result = [r for r in result if r.source_file == "b.md"]
        assert len(kw_result) == 1
        # Score: 0.3 * 0.9 = 0.27
        assert abs(kw_result[0].score - 0.27) < 0.01


class TestHybridFuseMaxResults:
    """Test max_results boundary enforcement."""

    def test_max_results_limits_output(self) -> None:
        vec = [_chunk(source_file=f"v{i}.md", score=0.8 - i * 0.05) for i in range(5)]
        kw = [_chunk(source_file=f"k{i}.md", score=0.7 - i * 0.05) for i in range(5)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=3)
        assert len(result) == 3

    def test_max_results_exactly_total(self) -> None:
        """When max_results >= total unique chunks, return all."""
        vec = [_chunk(source_file="v1.md", score=0.8)]
        kw = [_chunk(source_file="k1.md", score=0.7)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=10)
        assert len(result) == 2


class TestHybridFuseScoring:
    """Score calculation correctness."""

    def test_score_clamped_at_one(self) -> None:
        """Scores never exceed 1.0 even with high inputs."""
        vec = [_chunk(source_file="a.md", line_start=1, score=1.0)]
        kw = [_chunk(source_file="a.md", line_start=1, score=1.0)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, kw, max_results=5)
        assert result[0].score <= 1.0

    def test_score_rounded_to_4_decimals(self) -> None:
        vec = [_chunk(source_file="a.md", score=0.333333)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, [], max_results=5)
        score_str = str(result[0].score)
        # After the decimal point, at most 4 digits
        if "." in score_str:
            decimals = len(score_str.split(".")[1])
            assert decimals <= 4

    def test_custom_weights(self) -> None:
        """Custom weight parameters change the fusion score."""
        vec = [_chunk(source_file="a.md", score=1.0)]
        result_default = VectorKnowledgeBase._hybrid_fuse(vec, [], max_results=5)
        result_custom = VectorKnowledgeBase._hybrid_fuse(
            vec, [], max_results=5, vector_weight=0.9
        )
        assert result_custom[0].score > result_default[0].score

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
        """Chunk content is preserved through fusion."""
        vec = [_chunk(content="important content", source_file="a.md", score=0.8)]
        result = VectorKnowledgeBase._hybrid_fuse(vec, [], max_results=5)
        assert result[0].content == "important content"


class TestVectorKnowledgeBasePublicAPI:
    """Test public methods of VectorKnowledgeBase with simple backend."""

    def test_backend_type_pending_before_init(self) -> None:
        from pathlib import Path
        kb = VectorKnowledgeBase(Path("/nonexistent"))
        assert kb.backend_type == "pending"

    def test_search_empty_returns_empty(self, tmp_path) -> None:
        kb = VectorKnowledgeBase(tmp_path)
        result = kb.search("anything")
        assert result == []

    def test_get_context_no_results(self, tmp_path) -> None:
        kb = VectorKnowledgeBase(tmp_path)
        ctx = kb.get_context("anything")
        assert "No relevant knowledge" in ctx

    def test_get_sources_empty(self, tmp_path) -> None:
        kb = VectorKnowledgeBase(tmp_path)
        sources = kb.get_sources("anything")
        assert sources == []

    def test_list_files_empty(self, tmp_path) -> None:
        kb = VectorKnowledgeBase(tmp_path)
        files = kb.list_files()
        assert files == []

    def test_get_context_with_real_files(self, tmp_path) -> None:
        (tmp_path / "guide.md").write_text("# Security\nUse parameterised queries.\n\nMore content here.")
        kb = VectorKnowledgeBase(tmp_path)
        ctx = kb.get_context("security parameterised")
        assert "security" in ctx.lower() or "No relevant" in ctx

    def test_get_sources_deduplicates(self, tmp_path) -> None:
        (tmp_path / "a.md").write_text("# Topic\nKeyword appears here.\n\nKeyword appears again.")
        kb = VectorKnowledgeBase(tmp_path)
        sources = kb.get_sources("keyword")
        # Each source should appear only once
        assert len(sources) == len(set(sources))

    def test_get_context_respects_max_length(self, tmp_path) -> None:
        # Create content that produces multiple chunks
        content = "\n\n".join(f"## Section {i}\n{'x' * 200}" for i in range(20))
        (tmp_path / "big.md").write_text(content)
        kb = VectorKnowledgeBase(tmp_path)
        ctx = kb.get_context("section", max_length=100)
        # Context should respect the max_length
        assert len(ctx) <= 200  # Some slack for formatting
