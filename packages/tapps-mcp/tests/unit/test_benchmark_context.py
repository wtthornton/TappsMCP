"""Unit tests for benchmark context injection engine (Epic 30, Story 3)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.benchmark.context_injector import (
    ContextInjector,
    RedundancyAnalyzer,
    SectionRedundancy,
    _jaccard_similarity,
    _tokenize,
)

# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestTokenize:
    """Tests for the _tokenize helper."""

    def test_tokenize_basic(self) -> None:
        tokens = _tokenize("Hello World foo BAR")
        assert tokens == {"hello", "world", "foo", "bar"}

    def test_tokenize_strips_punctuation(self) -> None:
        tokens = _tokenize("hello, world! foo-bar.")
        assert tokens == {"hello", "world", "foo", "bar"}

    def test_tokenize_empty_string(self) -> None:
        assert _tokenize("") == set()

    def test_jaccard_identical_sets(self) -> None:
        s = {"a", "b", "c"}
        assert _jaccard_similarity(s, s) == 1.0

    def test_jaccard_disjoint_sets(self) -> None:
        assert _jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_jaccard_empty_sets(self) -> None:
        assert _jaccard_similarity(set(), set()) == 0.0

    def test_jaccard_partial_overlap(self) -> None:
        # {a, b, c} & {b, c, d} = {b, c} => 2/4 = 0.5
        score = _jaccard_similarity({"a", "b", "c"}, {"b", "c", "d"})
        assert score == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# ContextInjector tests
# ---------------------------------------------------------------------------

_FAKE_TEMPLATE = "# AGENTS.md\n\n## Quality Pipeline\nUse tapps tools."


class TestContextInjector:
    """Tests for ContextInjector."""

    @patch(
        "tapps_mcp.benchmark.context_injector.load_agents_template",
        return_value=_FAKE_TEMPLATE,
    )
    def test_generate_returns_nonempty_template(
        self, mock_load: object, tmp_path: Path
    ) -> None:
        injector = ContextInjector(engagement_level="medium")
        content = injector.generate_tapps_context(tmp_path)
        assert len(content) > 0
        assert "AGENTS.md" in content

    @patch(
        "tapps_mcp.benchmark.context_injector.load_agents_template",
        return_value=_FAKE_TEMPLATE,
    )
    def test_generate_uses_engagement_level(
        self, mock_load: object, tmp_path: Path
    ) -> None:
        injector = ContextInjector(engagement_level="high")
        injector.generate_tapps_context(tmp_path)
        from tapps_mcp.benchmark.context_injector import (
            load_agents_template as patched,
        )

        patched.assert_called_once_with("high")  # type: ignore[union-attr]

    def test_inject_creates_file(self, tmp_path: Path) -> None:
        injector = ContextInjector()
        result = injector.inject_context(tmp_path, "test content")
        assert result == tmp_path / "AGENTS.md"
        assert result.read_text(encoding="utf-8") == "test content"

    def test_inject_custom_filename(self, tmp_path: Path) -> None:
        injector = ContextInjector()
        result = injector.inject_context(
            tmp_path, "custom", filename="CLAUDE.md"
        )
        assert result == tmp_path / "CLAUDE.md"
        assert result.read_text(encoding="utf-8") == "custom"

    def test_inject_backs_up_existing(self, tmp_path: Path) -> None:
        existing = tmp_path / "AGENTS.md"
        existing.write_text("original content", encoding="utf-8")

        injector = ContextInjector()
        injector.inject_context(tmp_path, "new content")

        backup = tmp_path / "AGENTS.md.bak"
        assert backup.read_text(encoding="utf-8") == "original content"
        assert existing.read_text(encoding="utf-8") == "new content"

    def test_remove_deletes_file(self, tmp_path: Path) -> None:
        target = tmp_path / "AGENTS.md"
        target.write_text("injected", encoding="utf-8")

        injector = ContextInjector()
        injector.remove_context(tmp_path)

        assert not target.exists()

    def test_remove_restores_backup(self, tmp_path: Path) -> None:
        target = tmp_path / "AGENTS.md"
        backup = tmp_path / "AGENTS.md.bak"
        target.write_text("injected", encoding="utf-8")
        backup.write_text("original", encoding="utf-8")

        injector = ContextInjector()
        injector.remove_context(tmp_path)

        assert target.read_text(encoding="utf-8") == "original"
        assert not backup.exists()

    def test_remove_nonexistent_is_noop(self, tmp_path: Path) -> None:
        injector = ContextInjector()
        # Should not raise
        injector.remove_context(tmp_path)
        assert not (tmp_path / "AGENTS.md").exists()


# ---------------------------------------------------------------------------
# RedundancyAnalyzer tests
# ---------------------------------------------------------------------------


class TestRedundancyAnalyzer:
    """Tests for RedundancyAnalyzer."""

    def test_identical_content_high_score(self) -> None:
        analyzer = RedundancyAnalyzer()
        text = "the quick brown fox jumps over the lazy dog"
        score = analyzer.score_redundancy(text, [text])
        assert score == pytest.approx(1.0)

    def test_completely_different_low_score(self) -> None:
        analyzer = RedundancyAnalyzer()
        agents = "alpha bravo charlie delta echo foxtrot"
        docs = ["golf hotel india juliet kilo lima"]
        score = analyzer.score_redundancy(agents, docs)
        assert score == pytest.approx(0.0)

    def test_partial_overlap_medium_score(self) -> None:
        analyzer = RedundancyAnalyzer()
        agents = "python testing quality security linting formatting"
        docs = ["python testing documentation coverage deployment"]
        score = analyzer.score_redundancy(agents, docs)
        assert 0.1 < score < 0.9

    def test_empty_docs_returns_zero(self) -> None:
        analyzer = RedundancyAnalyzer()
        assert analyzer.score_redundancy("some content", []) == 0.0

    def test_collect_repo_docs_reads_readme(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("# My Project\nDescription here.", encoding="utf-8")

        analyzer = RedundancyAnalyzer()
        docs = analyzer.collect_repo_docs(tmp_path)
        assert len(docs) == 1
        assert "My Project" in docs[0]

    def test_collect_repo_docs_reads_multiple(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("readme", encoding="utf-8")
        (tmp_path / "CONTRIBUTING.md").write_text("contrib", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("claude", encoding="utf-8")

        analyzer = RedundancyAnalyzer()
        docs = analyzer.collect_repo_docs(tmp_path)
        assert len(docs) == 3

    def test_collect_repo_docs_handles_missing(self, tmp_path: Path) -> None:
        analyzer = RedundancyAnalyzer()
        docs = analyzer.collect_repo_docs(tmp_path)
        assert docs == []

    def test_collect_repo_docs_reads_pyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "foo"\n'
            'description = "A test project"\n',
            encoding="utf-8",
        )
        analyzer = RedundancyAnalyzer()
        docs = analyzer.collect_repo_docs(tmp_path)
        assert len(docs) == 1
        assert docs[0] == "A test project"

    def test_analyze_sections_splits_on_headers(self) -> None:
        agents_md = (
            "# Title\nPreamble text.\n\n"
            "## Section A\nContent A words here.\n\n"
            "## Section B\nContent B other words.\n"
        )
        analyzer = RedundancyAnalyzer()
        results = analyzer.analyze_sections(agents_md, [])
        names = [r.section_name for r in results]
        assert "_preamble" in names
        assert "Section A" in names
        assert "Section B" in names

    def test_analyze_sections_recommendations(self) -> None:
        # Create agents_md with sections that have known overlap
        agents_md = (
            "## Unique\nalpha bravo charlie delta echo foxtrot golf\n\n"
            "## Overlapping\nthe quick brown fox jumps lazy dog\n\n"
            "## Identical\nxray yankee zulu whiskey tango uniform\n"
        )
        # repo_docs that match some sections heavily
        repo_docs = ["the quick brown fox jumps over the lazy dog"]

        analyzer = RedundancyAnalyzer()
        results = analyzer.analyze_sections(agents_md, repo_docs)

        by_name = {r.section_name: r for r in results}

        # "Unique" section should have low overlap -> "keep"
        assert by_name["Unique"].recommendation == "keep"
        assert by_name["Unique"].redundancy_score < 0.3

    def test_analyze_sections_empty_agents_md(self) -> None:
        analyzer = RedundancyAnalyzer()
        results = analyzer.analyze_sections("", [])
        assert results == []


# ---------------------------------------------------------------------------
# SectionRedundancy model tests
# ---------------------------------------------------------------------------


class TestSectionRedundancy:
    """Tests for SectionRedundancy Pydantic model."""

    def test_valid_creation(self) -> None:
        sr = SectionRedundancy(
            section_name="Test",
            redundancy_score=0.42,
            recommendation="reduce",
        )
        assert sr.section_name == "Test"
        assert sr.redundancy_score == pytest.approx(0.42)
        assert sr.recommendation == "reduce"

    def test_frozen(self) -> None:
        sr = SectionRedundancy(
            section_name="Test",
            redundancy_score=0.5,
            recommendation="keep",
        )
        with pytest.raises(Exception):  # noqa: B017
            sr.section_name = "Changed"  # type: ignore[misc]

    def test_score_bounds(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            SectionRedundancy(
                section_name="Bad",
                redundancy_score=1.5,
                recommendation="keep",
            )
