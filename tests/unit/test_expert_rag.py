"""Unit tests for tapps_mcp.experts.rag."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tapps_mcp.experts.rag import SimpleKnowledgeBase, _deduplicate, _extract_keywords

if TYPE_CHECKING:
    from pathlib import Path


class TestExtractKeywords:
    """Tests for _extract_keywords."""

    def test_stop_words_removed(self) -> None:
        kw = _extract_keywords("what is the best way to do this?")
        assert "the" not in kw
        assert "what" not in kw
        assert "best" in kw
        assert "way" in kw

    def test_short_words_removed(self) -> None:
        kw = _extract_keywords("do it or go")
        # "do", "it", "or" are stop words; "go" (2 chars) meets min keyword length.
        assert kw == {"go"}

    def test_preserves_compound_terms(self) -> None:
        kw = _extract_keywords("performance-optimization bottleneck")
        assert "performance-optimization" in kw
        assert "bottleneck" in kw

    def test_empty_query(self) -> None:
        assert _extract_keywords("") == set()


class TestSimpleKnowledgeBase:
    """Tests for SimpleKnowledgeBase."""

    def _create_kb(self, tmp_path: Path, files: dict[str, str]) -> SimpleKnowledgeBase:
        """Helper to create a knowledge base with given files."""
        for name, content in files.items():
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return SimpleKnowledgeBase(tmp_path)

    def test_loads_markdown_files(self, tmp_path: Path) -> None:
        kb = self._create_kb(
            tmp_path,
            {
                "guide.md": "# Security\nUse parameterised queries.",
                "tips.md": "# Performance\nProfile before optimising.",
            },
        )
        assert kb.file_count == 2

    def test_ignores_non_markdown(self, tmp_path: Path) -> None:
        kb = self._create_kb(
            tmp_path,
            {
                "guide.md": "# Hello",
                "data.json": '{"key": "value"}',
            },
        )
        assert kb.file_count == 1

    def test_search_returns_matching_chunks(self, tmp_path: Path) -> None:
        kb = self._create_kb(
            tmp_path,
            {
                "security.md": "# SQL Injection\nUse parameterised queries to prevent injection.",
            },
        )
        results = kb.search("sql injection prevention")
        assert len(results) > 0
        assert results[0].score > 0

    def test_search_empty_query(self, tmp_path: Path) -> None:
        kb = self._create_kb(tmp_path, {"guide.md": "# Hello\nWorld."})
        results = kb.search("")
        assert results == []

    def test_search_no_match(self, tmp_path: Path) -> None:
        kb = self._create_kb(tmp_path, {"guide.md": "# Hello\nWorld."})
        results = kb.search("zyxwvu nonexistent")
        assert results == []

    def test_search_respects_max_results(self, tmp_path: Path) -> None:
        content = "\n\n".join(f"## Section {i}\nKeyword match here." for i in range(20))
        kb = self._create_kb(tmp_path, {"big.md": content})
        results = kb.search("keyword match", max_results=3)
        assert len(results) <= 3

    def test_get_context_formats_output(self, tmp_path: Path) -> None:
        kb = self._create_kb(
            tmp_path,
            {
                "guide.md": "# Security Best Practices\nUse HTTPS everywhere.",
            },
        )
        ctx = kb.get_context("security https")
        assert "security" in ctx.lower()

    def test_get_context_no_match(self, tmp_path: Path) -> None:
        kb = self._create_kb(tmp_path, {"guide.md": "# Hello"})
        ctx = kb.get_context("zyxwvu nonexistent")
        assert "No relevant knowledge" in ctx

    def test_get_sources(self, tmp_path: Path) -> None:
        kb = self._create_kb(
            tmp_path,
            {
                "security.md": "# XSS Prevention\nSanitize all user input.",
            },
        )
        sources = kb.get_sources("xss sanitize")
        assert len(sources) > 0
        assert "security.md" in sources[0]

    def test_list_files(self, tmp_path: Path) -> None:
        kb = self._create_kb(
            tmp_path,
            {
                "a.md": "# A",
                "sub/b.md": "# B",
            },
        )
        files = kb.list_files()
        assert len(files) == 2

    def test_nonexistent_directory(self, tmp_path: Path) -> None:
        kb = SimpleKnowledgeBase(tmp_path / "nonexistent")
        assert kb.file_count == 0
        assert kb.search("anything") == []

    def test_domain_filter(self, tmp_path: Path) -> None:
        (tmp_path / "security-guide.md").write_text("# Security\nContent.")
        (tmp_path / "performance-guide.md").write_text("# Performance\nContent.")
        kb = SimpleKnowledgeBase(tmp_path, domain="security")
        assert kb.file_count == 1

    def test_header_boost(self, tmp_path: Path) -> None:
        kb = self._create_kb(
            tmp_path,
            {
                "guide.md": (
                    "# Authentication\n"
                    "Some filler text.\n"
                    "More filler.\n\n"
                    "Authentication is mentioned here too."
                ),
            },
        )
        results = kb.search("authentication")
        assert len(results) > 0
        # The chunk should include the header.
        assert "# Authentication" in results[0].content

    def test_large_file_skipped(self, tmp_path: Path) -> None:
        big_file = tmp_path / "huge.md"
        # Write > 10 MB.
        big_file.write_text("x" * (11 * 1024 * 1024), encoding="utf-8")
        kb = SimpleKnowledgeBase(tmp_path)
        assert kb.file_count == 0


class TestDeduplicate:
    """Tests for _deduplicate."""

    def test_no_duplicates(self) -> None:
        from tapps_mcp.experts.models import KnowledgeChunk

        chunks = [
            KnowledgeChunk(content="Alpha content", source_file="a.md", line_start=1, line_end=5),
            KnowledgeChunk(content="Beta content", source_file="b.md", line_start=1, line_end=5),
        ]
        result = _deduplicate(chunks)
        assert len(result) == 2

    def test_exact_duplicate_removed(self) -> None:
        from tapps_mcp.experts.models import KnowledgeChunk

        chunks = [
            KnowledgeChunk(content="Same content", source_file="a.md", line_start=1, line_end=5),
            KnowledgeChunk(content="Same content", source_file="b.md", line_start=1, line_end=5),
        ]
        result = _deduplicate(chunks)
        assert len(result) == 1

    def test_substring_duplicate_removed(self) -> None:
        from tapps_mcp.experts.models import KnowledgeChunk

        chunks = [
            KnowledgeChunk(
                content="This is a long piece of content with lots of words",
                source_file="a.md",
                line_start=1,
                line_end=5,
            ),
            KnowledgeChunk(
                content="long piece of content",
                source_file="b.md",
                line_start=1,
                line_end=3,
            ),
        ]
        result = _deduplicate(chunks)
        assert len(result) == 1

    def test_empty_list(self) -> None:
        assert _deduplicate([]) == []


class TestTestingKBRetrieval:
    """Validate that test-configuration-and-urls.md is retrievable for representative queries."""

    def test_base_url_config_returns_chunks(self) -> None:
        from pathlib import Path

        kb_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "src"
            / "tapps_mcp"
            / "experts"
            / "knowledge"
            / "testing"
        )
        kb = SimpleKnowledgeBase(kb_dir)
        results = kb.search("base URL configuration fixture")
        assert len(results) > 0
        assert any("url" in c.content.lower() or "base_url" in c.content.lower() for c in results)

    def test_monkeypatch_env_returns_chunks(self) -> None:
        from pathlib import Path

        kb_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "src"
            / "tapps_mcp"
            / "experts"
            / "knowledge"
            / "testing"
        )
        kb = SimpleKnowledgeBase(kb_dir)
        results = kb.search("monkeypatch environment variables")
        assert len(results) > 0
        assert any("monkeypatch" in c.content.lower() for c in results)

    def test_localhost_avoidance_returns_chunks(self) -> None:
        from pathlib import Path

        kb_dir = (
            Path(__file__).resolve().parent.parent.parent
            / "src"
            / "tapps_mcp"
            / "experts"
            / "knowledge"
            / "testing"
        )
        kb = SimpleKnowledgeBase(kb_dir)
        results = kb.search("avoid hardcoded localhost")
        assert len(results) > 0
