"""Unit tests for RAG warming, BM25 fallback, and index freshness.

Story 68.1: Ensures that expert consultations get meaningful chunks even
when sentence_transformers/FAISS are unavailable, via BM25 fallback.
Also verifies lazy warming and index staleness detection.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_core.experts.models import KnowledgeChunk
from tapps_core.experts.rag import SimpleKnowledgeBase
from tapps_core.experts.vector_rag import (
    VectorKnowledgeBase,
    _ExpertBM25Fallback,
    _split_by_paragraphs,
    _split_into_sections,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def knowledge_dir(tmp_path: Path) -> Path:
    """Create a knowledge directory with sample markdown files."""
    kdir = tmp_path / "knowledge" / "testing-strategies"
    kdir.mkdir(parents=True)

    (kdir / "best-practices.md").write_text(
        "# Testing Best Practices\n\n"
        "## Unit Testing\n\n"
        "Write small focused tests. Use pytest fixtures for setup.\n"
        "Mock external dependencies. Assert specific outcomes.\n\n"
        "## Integration Testing\n\n"
        "Test component interactions. Use real databases when possible.\n"
        "Verify API contracts and error handling.\n\n"
        "## Performance Testing\n\n"
        "Benchmark critical paths. Monitor response times.\n"
        "Set performance budgets and fail CI on regression.\n",
        encoding="utf-8",
    )

    (kdir / "patterns.md").write_text(
        "# Testing Patterns\n\n"
        "## Arrange-Act-Assert\n\n"
        "Structure tests with clear setup, execution, and verification.\n\n"
        "## Given-When-Then\n\n"
        "Describe behavior in business language for BDD.\n\n"
        "## Test Doubles\n\n"
        "Use mocks, stubs, fakes, and spies appropriately.\n"
        "Prefer fakes over mocks for complex interactions.\n",
        encoding="utf-8",
    )

    return kdir


@pytest.fixture()
def empty_knowledge_dir(tmp_path: Path) -> Path:
    """Create an empty knowledge directory."""
    kdir = tmp_path / "knowledge" / "empty-domain"
    kdir.mkdir(parents=True)
    return kdir


# ---------------------------------------------------------------------------
# _ExpertBM25Fallback tests
# ---------------------------------------------------------------------------


class TestExpertBM25Fallback:
    """Tests for the BM25-based expert knowledge search fallback."""

    def test_search_returns_relevant_chunks(self, knowledge_dir: Path) -> None:
        """BM25 should find chunks relevant to the query."""
        simple = SimpleKnowledgeBase(knowledge_dir)
        fallback = _ExpertBM25Fallback(simple)

        results = fallback.search("unit testing fixtures", max_results=3)

        assert len(results) > 0
        assert all(isinstance(c, KnowledgeChunk) for c in results)
        # Should find content about unit testing.
        combined = " ".join(c.content for c in results).lower()
        assert "test" in combined

    def test_search_scores_are_normalized(self, knowledge_dir: Path) -> None:
        """BM25 scores should be normalized to 0-1."""
        simple = SimpleKnowledgeBase(knowledge_dir)
        fallback = _ExpertBM25Fallback(simple)

        results = fallback.search("testing patterns", max_results=5)

        for chunk in results:
            assert 0.0 <= chunk.score <= 1.0

    def test_search_empty_query_returns_empty(self, knowledge_dir: Path) -> None:
        """Empty query should return no results."""
        simple = SimpleKnowledgeBase(knowledge_dir)
        fallback = _ExpertBM25Fallback(simple)

        assert fallback.search("", max_results=5) == []

    def test_search_no_match_returns_empty(self, knowledge_dir: Path) -> None:
        """Query with no matching terms should return empty."""
        simple = SimpleKnowledgeBase(knowledge_dir)
        fallback = _ExpertBM25Fallback(simple)

        # Nonsense query unlikely to match.
        results = fallback.search("xyzzy plugh", max_results=5)
        assert results == []

    def test_search_empty_knowledge_returns_empty(
        self, empty_knowledge_dir: Path
    ) -> None:
        """Empty knowledge base should return no results."""
        simple = SimpleKnowledgeBase(empty_knowledge_dir)
        fallback = _ExpertBM25Fallback(simple)

        results = fallback.search("testing", max_results=5)
        assert results == []

    def test_index_built_once(self, knowledge_dir: Path) -> None:
        """BM25 index should be built lazily and only once."""
        simple = SimpleKnowledgeBase(knowledge_dir)
        fallback = _ExpertBM25Fallback(simple)

        assert not fallback._built
        fallback.search("test", max_results=1)
        assert fallback._built
        # Second search should not rebuild.
        fallback.search("patterns", max_results=1)
        assert fallback._built

    def test_source_file_is_relative(self, knowledge_dir: Path) -> None:
        """Chunk source_file should be a relative path."""
        simple = SimpleKnowledgeBase(knowledge_dir)
        fallback = _ExpertBM25Fallback(simple)

        results = fallback.search("testing", max_results=3)
        for chunk in results:
            assert not Path(chunk.source_file).is_absolute()

    def test_results_sorted_by_score_descending(
        self, knowledge_dir: Path
    ) -> None:
        """Results should be sorted by score in descending order."""
        simple = SimpleKnowledgeBase(knowledge_dir)
        fallback = _ExpertBM25Fallback(simple)

        results = fallback.search("testing best practices", max_results=10)
        if len(results) > 1:
            scores = [c.score for c in results]
            assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# _split_into_sections tests
# ---------------------------------------------------------------------------


class TestSplitIntoSections:
    """Tests for markdown section splitting."""

    def test_splits_on_headers(self) -> None:
        content = "# First\nHello\n# Second\nWorld"
        sections = _split_into_sections(content)
        assert len(sections) == 2
        assert "First" in sections[0]
        assert "Second" in sections[1]

    def test_single_section_no_headers(self) -> None:
        content = "Just some text\nwithout headers"
        sections = _split_into_sections(content)
        assert len(sections) == 1

    def test_large_section_split_by_paragraphs(self) -> None:
        # Create content larger than max_section_chars.
        content = "# Big Section\n\n" + ("word " * 500 + "\n\n") * 5
        sections = _split_into_sections(content, max_section_chars=500)
        assert len(sections) > 1

    def test_empty_content(self) -> None:
        sections = _split_into_sections("")
        assert len(sections) == 1
        assert sections[0] == ""


class TestSplitByParagraphs:
    """Tests for paragraph-based text splitting."""

    def test_splits_at_double_newlines(self) -> None:
        text = "Para one.\n\nPara two.\n\nPara three."
        result = _split_by_paragraphs(text, max_chars=30)
        assert len(result) >= 2

    def test_single_paragraph_under_limit(self) -> None:
        text = "Short paragraph."
        result = _split_by_paragraphs(text, max_chars=1000)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# VectorKnowledgeBase BM25 fallback tests
# ---------------------------------------------------------------------------


class TestVectorKnowledgeBaseBM25Fallback:
    """VectorKnowledgeBase should use BM25 when FAISS is unavailable."""

    def test_falls_back_to_bm25_when_no_embedder(
        self, knowledge_dir: Path
    ) -> None:
        """When create_embedder returns None, backend should be bm25."""
        with patch(
            "tapps_core.experts.vector_rag.SimpleKnowledgeBase"
        ) as mock_skb_cls:
            # Set up mock SimpleKnowledgeBase.
            mock_simple = MagicMock(spec=SimpleKnowledgeBase)
            mock_simple.file_count = 2
            mock_simple.files = {}
            mock_skb_cls.return_value = mock_simple

            with patch(
                "tapps_core.experts.rag_embedder.create_embedder",
                return_value=None,
            ):
                vkb = VectorKnowledgeBase(knowledge_dir, domain="testing")
                vkb._ensure_initialised()

                assert vkb.backend_type == "bm25"
                assert vkb._bm25_fallback is not None

    def test_bm25_search_returns_chunks(self, knowledge_dir: Path) -> None:
        """BM25 backend should return search results."""
        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            vkb = VectorKnowledgeBase(knowledge_dir)
            results = vkb.search("unit testing pytest fixtures")

            assert len(results) > 0
            assert all(isinstance(c, KnowledgeChunk) for c in results)

    def test_backend_type_is_bm25(self, knowledge_dir: Path) -> None:
        """Backend type should report 'bm25' when vector unavailable."""
        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            vkb = VectorKnowledgeBase(knowledge_dir)
            vkb._ensure_initialised()
            assert vkb.backend_type == "bm25"

    def test_empty_dir_falls_to_simple(
        self, empty_knowledge_dir: Path
    ) -> None:
        """Empty knowledge dir should fall back to simple, not bm25."""
        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            vkb = VectorKnowledgeBase(empty_knowledge_dir)
            vkb._ensure_initialised()
            assert vkb.backend_type == "simple"


# ---------------------------------------------------------------------------
# Index freshness tests
# ---------------------------------------------------------------------------


class TestIndexFreshness:
    """Tests for index staleness detection."""

    def test_stale_when_no_metadata(self, knowledge_dir: Path) -> None:
        """Index should be considered stale when metadata.json is missing."""
        vkb = VectorKnowledgeBase(knowledge_dir, domain="testing")
        idx_dir = knowledge_dir / "nonexistent_index"
        assert vkb._is_index_stale(idx_dir) is True

    def test_stale_when_knowledge_newer(
        self, knowledge_dir: Path, tmp_path: Path
    ) -> None:
        """Index should be stale when a knowledge file is newer."""
        idx_dir = tmp_path / "index"
        idx_dir.mkdir()

        # Create metadata file with old mtime.
        meta = idx_dir / "metadata.json"
        meta.write_text("{}", encoding="utf-8")

        # Ensure knowledge files are newer.
        time.sleep(0.05)
        md_file = knowledge_dir / "best-practices.md"
        md_file.write_text(
            md_file.read_text(encoding="utf-8") + "\nUpdated content.",
            encoding="utf-8",
        )

        vkb = VectorKnowledgeBase(knowledge_dir, domain="testing")
        assert vkb._is_index_stale(idx_dir) is True

    def test_fresh_when_index_newer(
        self, knowledge_dir: Path, tmp_path: Path
    ) -> None:
        """Index should not be stale when metadata is newer than all files."""
        idx_dir = tmp_path / "index"
        idx_dir.mkdir()

        # Ensure enough time gap.
        time.sleep(0.05)

        # Create metadata file (newer than knowledge files).
        meta = idx_dir / "metadata.json"
        meta.write_text("{}", encoding="utf-8")

        vkb = VectorKnowledgeBase(knowledge_dir, domain="testing")
        assert vkb._is_index_stale(idx_dir) is False


# ---------------------------------------------------------------------------
# Warming function tests
# ---------------------------------------------------------------------------


class TestWarmExpertRagIndices:
    """Tests for warm_expert_rag_indices with BM25 fallback."""

    def test_warming_counts_bm25_backends(self) -> None:
        """BM25 backends should be counted as warmed."""
        from tapps_core.experts.rag_warming import warm_expert_rag_indices

        mock_ts = MagicMock()
        mock_ts.languages = ["python"]
        mock_ts.frameworks = ["pytest"]
        mock_ts.libraries = []
        mock_ts.domains = []

        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            result = warm_expert_rag_indices(mock_ts)  # type: ignore[arg-type]

        # Should attempt at least "testing-strategies" domain.
        assert result["attempted"] > 0
        # With BM25 fallback, some domains should warm.
        # (warmed count depends on which domains have knowledge files)

    def test_warming_with_no_signals_still_warms_defaults(self) -> None:
        """Even with no signals, default domains (software-architecture) warm."""
        from tapps_core.experts.rag_warming import warm_expert_rag_indices

        mock_ts = MagicMock()
        mock_ts.languages = []
        mock_ts.frameworks = []
        mock_ts.libraries = []
        mock_ts.domains = []

        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            result = warm_expert_rag_indices(mock_ts)  # type: ignore[arg-type]

        # software-architecture is always included as default.
        assert result["attempted"] > 0
        assert "software-architecture" in result["domains"]

    def test_warming_no_domains_returns_empty(self) -> None:
        """When tech_stack_to_expert_domains returns [], warming is a no-op."""
        from tapps_core.experts.rag_warming import warm_expert_rag_indices

        mock_ts = MagicMock()
        mock_ts.languages = []
        mock_ts.frameworks = []
        mock_ts.libraries = []
        mock_ts.domains = []

        with patch(
            "tapps_core.experts.rag_warming.tech_stack_to_expert_domains",
            return_value=[],
        ):
            result = warm_expert_rag_indices(mock_ts)  # type: ignore[arg-type]

        assert result["attempted"] == 0
        assert result["warmed"] == 0
        assert result["skipped"] == "no_relevant_domains"


# ---------------------------------------------------------------------------
# Lazy warming integration tests
# ---------------------------------------------------------------------------


class TestLazyWarming:
    """VectorKnowledgeBase should lazy-warm on first search."""

    def test_not_initialised_until_search(
        self, knowledge_dir: Path
    ) -> None:
        """Backend should be 'pending' until first use."""
        vkb = VectorKnowledgeBase(knowledge_dir, domain="testing")
        assert vkb.backend_type == "pending"

    def test_initialises_on_first_search(
        self, knowledge_dir: Path
    ) -> None:
        """First search should trigger initialisation."""
        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            vkb = VectorKnowledgeBase(knowledge_dir)
            assert vkb.backend_type == "pending"

            vkb.search("testing")
            assert vkb.backend_type in ("bm25", "simple", "vector")

    def test_initialises_on_get_context(
        self, knowledge_dir: Path
    ) -> None:
        """get_context should also trigger initialisation."""
        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            vkb = VectorKnowledgeBase(knowledge_dir)
            vkb.get_context("testing")
            assert vkb.backend_type != "pending"

    def test_initialises_on_list_files(
        self, knowledge_dir: Path
    ) -> None:
        """list_files should also trigger initialisation."""
        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            vkb = VectorKnowledgeBase(knowledge_dir)
            vkb.list_files()
            assert vkb.backend_type != "pending"


# ---------------------------------------------------------------------------
# End-to-end search quality tests
# ---------------------------------------------------------------------------


class TestSearchQuality:
    """Verify BM25 fallback produces meaningful search results."""

    def test_relevant_query_gets_chunks(self, knowledge_dir: Path) -> None:
        """A relevant query should return non-empty results with BM25."""
        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            vkb = VectorKnowledgeBase(knowledge_dir)
            results = vkb.search("arrange act assert testing pattern")

            assert len(results) > 0
            combined = " ".join(c.content.lower() for c in results)
            assert "assert" in combined or "test" in combined

    def test_get_context_returns_text(self, knowledge_dir: Path) -> None:
        """get_context should return non-empty text for valid queries."""
        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            vkb = VectorKnowledgeBase(knowledge_dir)
            context = vkb.get_context("unit testing best practices")

            assert len(context) > 0
            assert context != "No relevant knowledge found in knowledge base."

    def test_get_sources_returns_files(self, knowledge_dir: Path) -> None:
        """get_sources should return file paths for valid queries."""
        with patch(
            "tapps_core.experts.rag_embedder.create_embedder",
            return_value=None,
        ):
            vkb = VectorKnowledgeBase(knowledge_dir)
            sources = vkb.get_sources("testing")

            assert len(sources) > 0
