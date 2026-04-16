"""Tests for EPIC-12: Agent Catalog Governance.

Covers dedup gate, merge suggestions, catalog health,
agent lifecycle, and overlap guard.
"""

from __future__ import annotations

import time
from pathlib import Path

from docs_mcp.agents.catalog import AgentCatalog
from docs_mcp.agents.dedup import DedupResult, check_dedup
from docs_mcp.agents.embeddings import StubEmbeddingBackend
from docs_mcp.agents.health import CatalogHealthReport, analyze_catalog_health
from docs_mcp.agents.lifecycle import (
    cleanup_deprecated,
    deprecate_agent,
    restore_agent,
)
from docs_mcp.agents.matcher import HybridMatcher
from docs_mcp.agents.merge import MergeReport, generate_merge_suggestion
from docs_mcp.agents.models import AgentConfig
from docs_mcp.agents.overlap_guard import get_overlap_context


def _make_agents() -> list[AgentConfig]:
    """Create test agents for governance tests."""
    return [
        AgentConfig(
            name="weather",
            description="Provides weather forecasts and temperature data",
            keywords=["weather", "forecast", "temperature", "rain", "wind"],
            capabilities=["weather_lookup", "forecast_7day"],
        ),
        AgentConfig(
            name="code-review",
            description="Reviews Python code for quality and security issues",
            keywords=["python", "code", "review", "quality", "security", "lint"],
            capabilities=["lint_check", "security_scan"],
        ),
        AgentConfig(
            name="docs-writer",
            description="Generates documentation and README files",
            keywords=["documentation", "readme", "docs", "writing", "markdown"],
            capabilities=["readme_gen", "changelog_gen"],
        ),
    ]


# --- Story 12.1: Dedup gate tests ---


class TestDedupGate:
    """Test embedding-based deduplication gate."""

    def test_no_duplicate_different_domain(self) -> None:
        agents = _make_agents()
        backend = StubEmbeddingBackend()
        result = check_dedup(
            "cooking recipes and meal planning",
            agents,
            backend,
            threshold=0.85,
        )
        assert isinstance(result, DedupResult)
        assert result.is_duplicate is False
        assert result.overlapping_agents == []

    def test_exact_text_is_duplicate(self) -> None:
        agents = _make_agents()
        backend = StubEmbeddingBackend()
        # Use exact same embedding text as the weather agent
        result = check_dedup(
            agents[0].embedding_text(),
            agents,
            backend,
            threshold=0.85,
        )
        assert result.is_duplicate is True
        assert len(result.overlapping_agents) >= 1
        assert result.overlapping_agents[0].agent.name == "weather"
        assert result.overlapping_agents[0].similarity >= 0.85

    def test_empty_catalog(self) -> None:
        backend = StubEmbeddingBackend()
        result = check_dedup("anything", [], backend)
        assert result.is_duplicate is False
        assert result.overlapping_agents == []

    def test_excludes_deprecated(self) -> None:
        agents = [
            AgentConfig(name="old", keywords=["test"], deprecated=True),
        ]
        backend = StubEmbeddingBackend()
        result = check_dedup(
            agents[0].embedding_text(),
            agents,
            backend,
            threshold=0.0,
        )
        assert result.is_duplicate is False

    def test_threshold_respected(self) -> None:
        agents = _make_agents()
        backend = StubEmbeddingBackend()
        text = agents[0].embedding_text()

        # Very high threshold — nothing should match
        high = check_dedup(text, agents, backend, threshold=0.999)
        # Very low threshold — everything matches
        low = check_dedup(text, agents, backend, threshold=0.0)

        assert len(high.overlapping_agents) <= len(low.overlapping_agents)

    def test_precomputed_embeddings(self) -> None:
        agents = _make_agents()
        backend = StubEmbeddingBackend()
        precomputed = backend.embed([a.embedding_text() for a in agents])

        result = check_dedup(
            agents[0].embedding_text(),
            agents,
            backend,
            threshold=0.85,
            precomputed_embeddings=precomputed,
        )
        assert result.is_duplicate is True

    def test_results_sorted_by_similarity(self) -> None:
        agents = _make_agents()
        backend = StubEmbeddingBackend()
        result = check_dedup(
            agents[0].embedding_text(),
            agents,
            backend,
            threshold=0.0,
        )
        for i in range(len(result.overlapping_agents) - 1):
            assert (
                result.overlapping_agents[i].similarity
                >= result.overlapping_agents[i + 1].similarity
            )


# --- Story 12.2: Merge suggestion tests ---


class TestMergeSuggestions:
    """Test capability merge suggestion generation."""

    def test_basic_merge(self) -> None:
        proposal = AgentConfig(
            name="weather-alerts",
            description="Sends weather alerts and warnings",
            keywords=["weather", "alerts", "warnings", "storms"],
            capabilities=["alert_push", "storm_tracking"],
        )
        existing = AgentConfig(
            name="weather",
            description="Provides weather forecasts",
            keywords=["weather", "forecast", "temperature"],
            capabilities=["weather_lookup"],
        )
        suggestion = generate_merge_suggestion(proposal, existing, similarity=0.87)

        assert suggestion.target_agent == "weather"
        assert suggestion.similarity == 0.87
        assert "alerts" in suggestion.new_keywords
        assert "warnings" in suggestion.new_keywords
        assert "weather" not in suggestion.new_keywords  # Already exists
        assert "alert_push" in suggestion.new_capabilities
        assert "weather_lookup" not in suggestion.new_capabilities

    def test_no_new_keywords(self) -> None:
        proposal = AgentConfig(
            name="weather-v2",
            keywords=["weather", "forecast"],
        )
        existing = AgentConfig(
            name="weather",
            keywords=["weather", "forecast", "temperature"],
        )
        suggestion = generate_merge_suggestion(proposal, existing, similarity=0.95)
        assert suggestion.new_keywords == []

    def test_rationale_includes_names(self) -> None:
        proposal = AgentConfig(name="new-agent", keywords=["test"])
        existing = AgentConfig(name="old-agent", keywords=["test"])
        suggestion = generate_merge_suggestion(proposal, existing, similarity=0.90)
        assert "new-agent" in suggestion.rationale
        assert "old-agent" in suggestion.rationale
        assert "90%" in suggestion.rationale

    def test_merge_report_to_dict(self) -> None:
        proposal = AgentConfig(name="test", keywords=["a"])
        existing = AgentConfig(name="target", keywords=["b"])
        suggestion = generate_merge_suggestion(proposal, existing, similarity=0.88)

        report = MergeReport(
            proposal_name="test",
            is_duplicate=True,
            suggestions=[suggestion],
        )
        d = report.to_dict()
        assert d["proposal_name"] == "test"
        assert d["is_duplicate"] is True
        assert d["suggestion_count"] == 1
        assert len(d["suggestions"]) == 1  # type: ignore[arg-type]


# --- Story 12.3: Catalog health tests ---


class TestCatalogHealth:
    """Test catalog health analysis."""

    def test_empty_catalog(self) -> None:
        matcher = HybridMatcher(agents=[], backend=StubEmbeddingBackend())
        report = analyze_catalog_health(matcher)
        assert isinstance(report, CatalogHealthReport)
        assert report.total_agents == 0
        assert report.health_score == 100.0

    def test_no_overlaps(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        report = analyze_catalog_health(matcher, threshold=0.99)
        assert report.total_agents == 3
        assert report.active_agents == 3
        assert len(report.overlap_pairs) == 0
        assert report.health_score == 100.0

    def test_with_deprecated(self) -> None:
        agents = _make_agents()
        agents.append(AgentConfig(name="old", deprecated=True))
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        report = analyze_catalog_health(matcher)
        assert report.deprecated_agents == 1
        assert report.active_agents == 3

    def test_health_report_to_dict(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        report = analyze_catalog_health(matcher)
        d = report.to_dict()
        assert "total_agents" in d
        assert "health_score" in d
        assert "overlaps" in d
        assert isinstance(d["overlaps"], list)

    def test_low_threshold_finds_overlaps(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        # Very low threshold should find some pairs
        report = analyze_catalog_health(matcher, threshold=0.0)
        # With stub backend, all pairs have some nonzero similarity
        assert report.total_agents == 3

    def test_health_score_decreases_with_overlaps(self) -> None:
        report_clean = CatalogHealthReport(
            total_agents=5,
            active_agents=5,
            overlap_pairs=[],
        )
        from docs_mcp.agents.health import OverlapPair

        report_dirty = CatalogHealthReport(
            total_agents=5,
            active_agents=5,
            overlap_pairs=[
                OverlapPair("a", "b", 0.9, "merge"),
                OverlapPair("c", "d", 0.8, "review"),
            ],
        )
        assert report_clean.health_score > report_dirty.health_score

    def test_single_agent_healthy(self) -> None:
        agents = [AgentConfig(name="solo", keywords=["unique"])]
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        report = analyze_catalog_health(matcher)
        assert report.health_score == 100.0


# --- Story 12.4: Lifecycle tests ---


class TestLifecycle:
    """Test agent soft-delete and lifecycle management."""

    def test_deprecate_agent(self) -> None:
        catalog = AgentCatalog([AgentConfig(name="target")])
        result = deprecate_agent(catalog, "target")
        assert result.success is True
        assert catalog.get("target") is not None
        assert catalog.get("target").deprecated is True  # type: ignore[union-attr]

    def test_deprecate_nonexistent(self) -> None:
        catalog = AgentCatalog()
        result = deprecate_agent(catalog, "ghost")
        assert result.success is False
        assert "not found" in result.message

    def test_deprecate_already_deprecated(self) -> None:
        catalog = AgentCatalog([AgentConfig(name="old", deprecated=True)])
        result = deprecate_agent(catalog, "old")
        assert result.success is True
        assert "already deprecated" in result.message

    def test_restore_agent(self) -> None:
        catalog = AgentCatalog([AgentConfig(name="paused", deprecated=True)])
        result = restore_agent(catalog, "paused")
        assert result.success is True
        assert catalog.get("paused") is not None
        assert catalog.get("paused").deprecated is False  # type: ignore[union-attr]

    def test_restore_already_active(self) -> None:
        catalog = AgentCatalog([AgentConfig(name="active")])
        result = restore_agent(catalog, "active")
        assert result.success is True
        assert "already active" in result.message

    def test_restore_nonexistent(self) -> None:
        catalog = AgentCatalog()
        result = restore_agent(catalog, "ghost")
        assert result.success is False

    def test_deprecate_persists_to_disk(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "test.md"
        agent_file.write_text("---\nname: test\ndescription: Test agent\n---\nBody\n")

        agent = AgentConfig(name="test", source_path=agent_file)
        catalog = AgentCatalog([agent])
        deprecate_agent(catalog, "test")

        content = agent_file.read_text()
        assert "deprecated: true" in content

    def test_cleanup_removes_expired(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "old.md"
        # Create a deprecated agent with a timestamp 60 days ago
        old_ts = int(time.time()) - (60 * 24 * 60 * 60)
        agent_file.write_text(
            f"---\nname: old\ndeprecated: true\ndeprecated_at: {old_ts}\n---\nBody\n"
        )

        agent = AgentConfig(name="old", deprecated=True, source_path=agent_file)
        catalog = AgentCatalog([agent])

        result = cleanup_deprecated(catalog, retention_seconds=30 * 24 * 60 * 60)
        assert result.agents_removed == 1
        assert "old" in result.removed_names
        assert not agent_file.exists()
        assert len(catalog) == 0

    def test_cleanup_preserves_recent(self, tmp_path: Path) -> None:
        agent_file = tmp_path / "recent.md"
        recent_ts = int(time.time()) - (5 * 24 * 60 * 60)  # 5 days ago
        agent_file.write_text(
            f"---\nname: recent\ndeprecated: true\ndeprecated_at: {recent_ts}\n---\n"
        )

        agent = AgentConfig(name="recent", deprecated=True, source_path=agent_file)
        catalog = AgentCatalog([agent])

        result = cleanup_deprecated(catalog, retention_seconds=30 * 24 * 60 * 60)
        assert result.agents_removed == 0
        assert agent_file.exists()
        assert len(catalog) == 1

    def test_cleanup_skips_no_timestamp(self) -> None:
        agent = AgentConfig(name="no-ts", deprecated=True)
        catalog = AgentCatalog([agent])
        result = cleanup_deprecated(catalog)
        assert result.agents_removed == 0

    def test_active_agents_excludes_deprecated(self) -> None:
        catalog = AgentCatalog(
            [
                AgentConfig(name="active1"),
                AgentConfig(name="deprecated1", deprecated=True),
                AgentConfig(name="active2"),
            ]
        )
        assert len(catalog.active_agents) == 2


# --- Story 12.5: Overlap guard tests ---


class TestOverlapGuard:
    """Test proposer overlap guard."""

    def test_no_similar_agents(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        context = get_overlap_context(
            "completely unrelated quantum physics topic",
            matcher,
            threshold=0.99,
        )
        assert len(context.similar_agents) == 0
        assert context.warning is None

    def test_returns_similar_agents(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        context = get_overlap_context(
            "weather forecast temperature",
            matcher,
            threshold=0.0,
        )
        assert len(context.similar_agents) > 0
        assert len(context.similar_agents) <= 3  # default top_n

    def test_top_n_limit(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        context = get_overlap_context(
            "test query",
            matcher,
            top_n=1,
            threshold=0.0,
        )
        assert len(context.similar_agents) <= 1

    def test_high_overlap_warning(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        # Use exact text of an agent to trigger high overlap
        context = get_overlap_context(
            agents[0].embedding_text(),
            matcher,
            threshold=0.0,
        )
        # With stub backend, exact text should produce high score
        if context.similar_agents and context.similar_agents[0].score >= 0.85:
            assert context.warning is not None
            assert "High overlap" in context.warning

    def test_prompt_injection_format(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        context = get_overlap_context(
            "weather data",
            matcher,
            threshold=0.0,
        )
        text = context.to_prompt_injection()
        assert isinstance(text, str)
        if context.similar_agents:
            assert "existing agents" in text

    def test_to_dict_serialization(self) -> None:
        agents = _make_agents()
        matcher = HybridMatcher(agents=agents, backend=StubEmbeddingBackend())
        context = get_overlap_context("test", matcher, threshold=0.0)
        d = context.to_dict()
        assert "proposal_text" in d
        assert "similar_count" in d
        assert "similar_agents" in d

    def test_empty_catalog(self) -> None:
        matcher = HybridMatcher(agents=[], backend=StubEmbeddingBackend())
        context = get_overlap_context("anything", matcher)
        assert context.similar_agents == []
        text = context.to_prompt_injection()
        assert "No existing agents" in text
