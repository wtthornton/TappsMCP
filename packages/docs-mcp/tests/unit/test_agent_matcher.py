"""Tests for hybrid agent matcher."""

from __future__ import annotations

from docs_mcp.agents.embeddings import StubEmbeddingBackend, cosine_similarity
from docs_mcp.agents.keyword_matcher import keyword_score, tokenize
from docs_mcp.agents.matcher import HybridMatcher, MatchResult
from docs_mcp.agents.models import AgentConfig


# --- Keyword matcher tests ---


class TestTokenize:
    """Test text tokenization."""

    def test_basic(self) -> None:
        tokens = tokenize("Hello World")
        assert tokens == ["hello", "world"]

    def test_stopword_removal(self) -> None:
        tokens = tokenize("the quick brown fox is a test")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "a" not in tokens
        assert "quick" in tokens
        assert "brown" in tokens
        assert "fox" in tokens

    def test_hyphenated_tokens(self) -> None:
        tokens = tokenize("machine-learning API")
        assert "machine-learning" in tokens
        assert "api" in tokens

    def test_underscore_tokens(self) -> None:
        tokens = tokenize("api_key test_runner")
        assert "api_key" in tokens
        assert "test_runner" in tokens

    def test_empty_string(self) -> None:
        assert tokenize("") == []

    def test_only_stopwords(self) -> None:
        assert tokenize("the a an is") == []

    def test_punctuation_stripped(self) -> None:
        tokens = tokenize("hello, world! test.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens


class TestKeywordScore:
    """Test keyword overlap scoring."""

    def test_perfect_overlap(self) -> None:
        tokens = ["weather", "forecast"]
        score = keyword_score(tokens, tokens)
        assert score == 1.0

    def test_no_overlap(self) -> None:
        score = keyword_score(["weather"], ["cooking"])
        assert score == 0.0

    def test_partial_overlap(self) -> None:
        score = keyword_score(
            ["weather", "forecast", "rain"],
            ["weather", "temperature", "wind"],
        )
        assert 0.0 < score < 1.0

    def test_empty_query(self) -> None:
        score = keyword_score([], ["weather"])
        assert score == 0.0

    def test_empty_agent(self) -> None:
        score = keyword_score(["weather"], [])
        assert score == 0.0

    def test_both_empty(self) -> None:
        score = keyword_score([], [])
        assert score == 0.0


# --- Embedding tests ---


class TestStubEmbeddingBackend:
    """Test stub embedding backend."""

    def test_consistent_embeddings(self) -> None:
        backend = StubEmbeddingBackend(dimension=128)
        emb1 = backend.embed(["test"])[0]
        emb2 = backend.embed(["test"])[0]
        assert emb1 == emb2

    def test_different_texts_different_embeddings(self) -> None:
        backend = StubEmbeddingBackend(dimension=128)
        emb1 = backend.embed(["hello"])[0]
        emb2 = backend.embed(["world"])[0]
        assert emb1 != emb2

    def test_correct_dimension(self) -> None:
        backend = StubEmbeddingBackend(dimension=64)
        assert backend.dimension == 64
        emb = backend.embed(["test"])[0]
        assert len(emb) == 64

    def test_batch_embedding(self) -> None:
        backend = StubEmbeddingBackend()
        results = backend.embed(["a", "b", "c"])
        assert len(results) == 3

    def test_unit_vectors(self) -> None:
        """Stub embeddings should be normalized to unit length."""
        backend = StubEmbeddingBackend(dimension=128)
        emb = backend.embed(["test"])[0]
        norm = sum(v * v for v in emb) ** 0.5
        assert abs(norm - 1.0) < 1e-6


class TestCosineSimilarity:
    """Test cosine similarity computation."""

    def test_identical_vectors(self) -> None:
        vec = [0.5, 0.5, 0.5, 0.5]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self) -> None:
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors(self) -> None:
        vec_a = [1.0, 0.0]
        vec_b = [-1.0, 0.0]
        assert cosine_similarity(vec_a, vec_b) == pytest.approx(-1.0, abs=1e-6)

    def test_mismatched_dimensions(self) -> None:
        assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


# --- Hybrid matcher tests ---


def _make_agents() -> list[AgentConfig]:
    """Create test agents for matcher tests."""
    return [
        AgentConfig(
            name="weather",
            description="Provides weather forecasts and temperature data",
            keywords=["weather", "forecast", "temperature", "rain", "wind"],
        ),
        AgentConfig(
            name="code-review",
            description="Reviews Python code for quality and security issues",
            keywords=["python", "code", "review", "quality", "security", "lint"],
        ),
        AgentConfig(
            name="docs-writer",
            description="Generates documentation and README files",
            keywords=["documentation", "readme", "docs", "writing", "markdown"],
        ),
        AgentConfig(
            name="deprecated-agent",
            description="An old deprecated agent",
            keywords=["old"],
            deprecated=True,
        ),
    ]


class TestHybridMatcher:
    """Test HybridMatcher."""

    def test_match_with_stub_backend(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(
            agents=agents,
            backend=StubEmbeddingBackend(),
        )
        results = matcher.match("weather forecast today", threshold=0.0)
        assert len(results) > 0
        assert all(isinstance(r, MatchResult) for r in results)

    def test_excludes_deprecated(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(
            agents=agents,
            backend=StubEmbeddingBackend(),
        )
        results = matcher.match("old deprecated agent", threshold=0.0)
        agent_names = [r.agent.name for r in results]
        assert "deprecated-agent" not in agent_names

    def test_empty_agents(self) -> None:
        matcher = HybridMatcher(agents=[], backend=StubEmbeddingBackend())
        results = matcher.match("anything")
        assert results == []

    def test_max_results(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(
            agents=agents,
            backend=StubEmbeddingBackend(),
        )
        results = matcher.match("test query", threshold=0.0, max_results=2)
        assert len(results) <= 2

    def test_results_sorted_by_score(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(
            agents=agents,
            backend=StubEmbeddingBackend(),
        )
        results = matcher.match("weather forecast", threshold=0.0)
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_keyword_match_boosts_score(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(
            agents=agents,
            backend=StubEmbeddingBackend(),
        )
        results = matcher.match("weather forecast temperature", threshold=0.0)
        # Weather agent should rank highly because of keyword overlap
        if results:
            weather_results = [r for r in results if r.agent.name == "weather"]
            if weather_results:
                assert weather_results[0].keyword_score > 0

    def test_degraded_mode_no_backend(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=None)
        assert matcher.is_degraded is True
        # Should still work with keyword-only matching
        results = matcher.match("weather forecast", threshold=0.0)
        assert len(results) > 0

    def test_match_result_fields(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(
            agents=agents,
            backend=StubEmbeddingBackend(),
        )
        results = matcher.match("python code review", threshold=0.0)
        assert len(results) > 0
        result = results[0]
        assert hasattr(result, "agent")
        assert hasattr(result, "score")
        assert hasattr(result, "keyword_score")
        assert hasattr(result, "embedding_score")
        assert result.score >= 0

    def test_pairwise_similarity(self) -> None:
        agents = _make_agents()[:3]  # Exclude deprecated
        matcher = HybridMatcher(
            agents=agents,
            backend=StubEmbeddingBackend(),
        )
        pairs = matcher.pairwise_similarity()
        # 3 agents -> 3 pairs (3 choose 2)
        assert len(pairs) == 3
        for (name_a, name_b), sim in pairs.items():
            assert name_a < name_b  # Alphabetical ordering
            assert -1.0 <= sim <= 1.0

    def test_pairwise_empty(self) -> None:
        matcher = HybridMatcher(agents=[], backend=StubEmbeddingBackend())
        assert matcher.pairwise_similarity() == {}

    def test_threshold_filtering(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(
            agents=agents,
            backend=StubEmbeddingBackend(),
        )
        high_threshold = matcher.match("xyz completely unrelated", threshold=0.99)
        low_threshold = matcher.match("xyz completely unrelated", threshold=0.0)
        assert len(high_threshold) <= len(low_threshold)


class TestEmbeddingCache:
    """Test embedding cache."""

    def test_cache_put_get(self, tmp_path: Path) -> None:
        from docs_mcp.agents.embeddings import EmbeddingCache

        cache = EmbeddingCache(tmp_path / "cache")
        vector = [0.1, 0.2, 0.3]
        cache.put("test text", vector)
        result = cache.get("test text")
        assert result == vector

    def test_cache_miss(self, tmp_path: Path) -> None:
        from docs_mcp.agents.embeddings import EmbeddingCache

        cache = EmbeddingCache(tmp_path / "cache")
        assert cache.get("not cached") is None

    def test_get_or_compute(self, tmp_path: Path) -> None:
        from docs_mcp.agents.embeddings import EmbeddingCache

        cache = EmbeddingCache(tmp_path / "cache")
        backend = StubEmbeddingBackend(dimension=64)

        texts = ["hello", "world"]
        results = cache.get_or_compute(texts, backend)
        assert len(results) == 2
        assert len(results[0]) == 64

        # Second call should use cache
        results2 = cache.get_or_compute(texts, backend)
        assert results == results2

    def test_matcher_with_cache(self, tmp_path: Path) -> None:
        agents = [AgentConfig(name="test", keywords=["hello"])]
        matcher = HybridMatcher(
            agents=agents,
            backend=StubEmbeddingBackend(),
            cache_dir=tmp_path / "cache",
        )
        results = matcher.match("hello world", threshold=0.0)
        assert len(results) > 0


import pytest  # noqa: E402
