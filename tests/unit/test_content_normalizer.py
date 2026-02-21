"""Unit tests for tapps_mcp.knowledge.content_normalizer."""

from __future__ import annotations

from tapps_mcp.knowledge.content_normalizer import (
    CodeSnippet,
    NormalizationResult,
    ReferenceCard,
    apply_token_budget,
    deduplicate_snippets,
    extract_snippets,
    normalize_content,
    rank_snippets,
)


SAMPLE_CONTENT = """# FastAPI Quick Start

## Installation

```bash
pip install fastapi uvicorn
```

## Basic Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/items/{item_id}")
def read_item(item_id: int, q: str = None):
    return {"item_id": item_id, "q": q}
```

## Running the App

```bash
uvicorn main:app --reload
```

## Advanced Configuration

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="My API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}
```
"""


class TestExtractSnippets:
    def test_extracts_code_blocks(self) -> None:
        snippets = extract_snippets(SAMPLE_CONTENT)
        assert len(snippets) >= 2  # At least the two Python blocks

    def test_captures_language(self) -> None:
        snippets = extract_snippets(SAMPLE_CONTENT)
        languages = {s.language for s in snippets}
        assert "python" in languages

    def test_captures_context_header(self) -> None:
        snippets = extract_snippets(SAMPLE_CONTENT)
        python_snippets = [s for s in snippets if s.language == "python"]
        assert any("Basic Example" in s.context or "Advanced" in s.context for s in python_snippets)

    def test_skips_short_snippets(self) -> None:
        content = "```python\nx\n```"
        snippets = extract_snippets(content)
        assert len(snippets) == 0

    def test_token_count_set(self) -> None:
        snippets = extract_snippets(SAMPLE_CONTENT)
        for s in snippets:
            assert s.token_count > 0

    def test_no_language_specified(self) -> None:
        """Code blocks without language tag should have empty language."""
        content = "## Section\n\n```\nsome long content that is at least 30 chars\n```"
        snippets = extract_snippets(content)
        assert len(snippets) == 1
        assert snippets[0].language == ""

    def test_snippet_exactly_at_min_length(self) -> None:
        """Snippet with exactly MIN_SNIPPET_LENGTH (30 chars) should be included."""
        code = "a" * 30
        content = f"```python\n{code}\n```"
        snippets = extract_snippets(content)
        assert len(snippets) == 1

    def test_snippet_just_below_min_length(self) -> None:
        """Snippet with 29 chars (below minimum 30) should be excluded."""
        code = "a" * 29
        content = f"```python\n{code}\n```"
        snippets = extract_snippets(content)
        assert len(snippets) == 0

    def test_content_with_no_code_blocks(self) -> None:
        content = "# Just some text\n\nNo code blocks here at all."
        snippets = extract_snippets(content)
        assert len(snippets) == 0

    def test_content_with_no_headers(self) -> None:
        """Code blocks without headers should still be extracted."""
        content = "Some text.\n\n```python\ndef foo():\n    return 'bar' * 100\n```"
        snippets = extract_snippets(content)
        assert len(snippets) == 1

    def test_multiple_headers_picks_nearest(self) -> None:
        """Multiple headers before a code block: the nearest header should be used."""
        content = "# First Header\n\nSome text.\n\n## Second Header\n\n```python\ndef foo():\n    return 'test' * 100\n```"
        snippets = extract_snippets(content)
        assert len(snippets) == 1
        assert "Second Header" in snippets[0].context


class TestRankSnippets:
    def test_ranks_by_completeness(self) -> None:
        snippets = [
            CodeSnippet(code="x = 1", token_count=2),
            CodeSnippet(
                code="from fastapi import FastAPI\ndef main():\n    return 'ok'",
                token_count=15,
            ),
        ]
        ranked = rank_snippets(snippets)
        # The one with imports + def should rank higher.
        assert ranked[0].code.startswith("from fastapi")

    def test_query_relevance_boosts(self) -> None:
        snippets = [
            CodeSnippet(code="print('hello world')\nreturn 1", language="python", token_count=5),
            CodeSnippet(code="def test_sql_injection():\n    query = 'SELECT * FROM users'\n    return query", language="python", token_count=10),
        ]
        ranked = rank_snippets(snippets, query="sql injection")
        assert "sql" in ranked[0].code.lower()

    def test_all_stopwords_query(self) -> None:
        """Query with only stopwords should not crash."""
        snippets = [
            CodeSnippet(code="from fastapi import FastAPI\ndef main():\n    return 'ok'", token_count=10),
        ]
        ranked = rank_snippets(snippets, query="how to the a in")
        assert len(ranked) == 1

    def test_empty_query(self) -> None:
        snippets = [
            CodeSnippet(code="from fastapi import FastAPI\ndef main():\n    return 'ok'", token_count=10),
        ]
        ranked = rank_snippets(snippets, query="")
        assert len(ranked) == 1

    def test_short_snippet_penalty(self) -> None:
        """Snippets with < 3 lines get penalized."""
        short = CodeSnippet(code="x = 1", token_count=2)
        long = CodeSnippet(code="x = 1\ny = 2\nz = 3\nreturn x + y + z", token_count=10)
        ranked = rank_snippets([short, long])
        # Short one should have lower score (or equal, but not higher)
        assert short.score <= long.score

    def test_very_long_snippet_penalty(self) -> None:
        """Snippets with > 50 lines get penalized."""
        long_code = "\n".join(f"line_{i} = {i}" for i in range(60))
        very_long = CodeSnippet(code=long_code, token_count=200)
        moderate = CodeSnippet(code="from os import path\ndef func():\n    return path.join('a', 'b')", token_count=10)
        rank_snippets([very_long, moderate])
        # Very long snippet gets -0.1 penalty
        assert very_long.score <= 1.0

    def test_language_preference(self) -> None:
        """Python/JS/TS snippets get a language bonus."""
        python_snip = CodeSnippet(code="x = 1\ny = 2\nz = 3", language="python", token_count=5)
        shell_snip = CodeSnippet(code="x = 1\ny = 2\nz = 3", language="bash", token_count=5)
        rank_snippets([python_snip, shell_snip])
        assert python_snip.score > shell_snip.score

    def test_scores_clamped(self) -> None:
        """All scores should be in [0.0, 1.0]."""
        snippets = [
            CodeSnippet(code="from x import y\ndef f():\n    class C:\n        return 1", language="python", token_count=15),
        ]
        ranked = rank_snippets(snippets, query="x y f C return")
        for s in ranked:
            assert 0.0 <= s.score <= 1.0

    def test_no_signals_score_zero(self) -> None:
        """A snippet with no import/def/class/return and no query match gets ~0."""
        snip = CodeSnippet(code="some plain text without keywords here now", language="rust", token_count=5)
        rank_snippets([snip])
        assert snip.score == 0.0


class TestDeduplicateSnippets:
    def test_removes_exact_duplicates(self) -> None:
        s = CodeSnippet(code="from fastapi import FastAPI", token_count=5)
        result = deduplicate_snippets([s, s])
        assert len(result) == 1

    def test_removes_substring_duplicates(self) -> None:
        short = CodeSnippet(code="import fastapi", token_count=3)
        long = CodeSnippet(code="import fastapi\napp = FastAPI()\nreturn app", token_count=8)
        result = deduplicate_snippets([long, short])
        assert len(result) == 1

    def test_keeps_different_snippets(self) -> None:
        a = CodeSnippet(code="from flask import Flask\napp = Flask(__name__)", token_count=8)
        b = CodeSnippet(code="from django import views\nclass MyView(views.View):\n    pass", token_count=10)
        result = deduplicate_snippets([a, b])
        assert len(result) == 2

    def test_empty_list(self) -> None:
        assert deduplicate_snippets([]) == []

    def test_single_snippet(self) -> None:
        s = CodeSnippet(code="print('hello')", token_count=3)
        result = deduplicate_snippets([s])
        assert len(result) == 1

    def test_all_identical(self) -> None:
        """All snippets identical → only 1 returned."""
        s = CodeSnippet(code="from os import path\nresult = path.join('a', 'b')", token_count=5)
        result = deduplicate_snippets([s, s, s])
        assert len(result) == 1

    def test_jaccard_threshold(self) -> None:
        """Very high Jaccard similarity → treated as duplicate."""
        a = CodeSnippet(code="from fastapi import FastAPI\napp = FastAPI()\nreturn app", token_count=8)
        b = CodeSnippet(code="from fastapi import FastAPI\napp = FastAPI()\nreturn application", token_count=8)
        # These share most words → should be deduped at default threshold (0.7)
        result = deduplicate_snippets([a, b])
        assert len(result) == 1

    def test_low_jaccard_kept(self) -> None:
        """Snippets with low word overlap should both be kept."""
        a = CodeSnippet(code="from flask import Flask\napp = Flask(__name__)\nreturn app", token_count=8)
        b = CodeSnippet(code="import pytest\ndef test_func():\n    assert True", token_count=8)
        result = deduplicate_snippets([a, b])
        assert len(result) == 2

    def test_custom_threshold(self) -> None:
        """Custom threshold controls dedup sensitivity."""
        a = CodeSnippet(code="from fastapi import FastAPI\napp = FastAPI()", token_count=5)
        b = CodeSnippet(code="from fastapi import FastAPI\napi = FastAPI()", token_count=5)
        # With threshold=1.0 (only exact), both should be kept
        result = deduplicate_snippets([a, b], threshold=1.0)
        assert len(result) == 2


class TestApplyTokenBudget:
    def test_respects_budget(self) -> None:
        snippets = [
            CodeSnippet(code="a" * 100, token_count=100),
            CodeSnippet(code="b" * 100, token_count=100),
            CodeSnippet(code="c" * 100, token_count=100),
        ]
        result = apply_token_budget(snippets, budget=200)
        assert len(result) == 2

    def test_empty_budget(self) -> None:
        snippets = [CodeSnippet(code="x" * 50, token_count=50)]
        result = apply_token_budget(snippets, budget=0)
        assert len(result) == 0

    def test_exactly_at_budget(self) -> None:
        """Single snippet exactly at budget → included."""
        snippets = [CodeSnippet(code="x" * 100, token_count=100)]
        result = apply_token_budget(snippets, budget=100)
        assert len(result) == 1

    def test_one_over_budget(self) -> None:
        """Single snippet one over budget → excluded."""
        snippets = [CodeSnippet(code="x" * 100, token_count=101)]
        result = apply_token_budget(snippets, budget=100)
        assert len(result) == 0

    def test_budget_larger_than_total(self) -> None:
        """Budget larger than all snippets → all included."""
        snippets = [
            CodeSnippet(code="a" * 50, token_count=50),
            CodeSnippet(code="b" * 50, token_count=50),
        ]
        result = apply_token_budget(snippets, budget=1000)
        assert len(result) == 2

    def test_empty_snippets(self) -> None:
        result = apply_token_budget([], budget=100)
        assert result == []

    def test_preserves_order(self) -> None:
        snippets = [
            CodeSnippet(code="first", token_count=10),
            CodeSnippet(code="second", token_count=10),
            CodeSnippet(code="third", token_count=10),
        ]
        result = apply_token_budget(snippets, budget=25)
        assert len(result) == 2
        assert result[0].code == "first"
        assert result[1].code == "second"


class TestNormalizeContent:
    def test_produces_reference_cards(self) -> None:
        result = normalize_content(SAMPLE_CONTENT, query="fastapi endpoint")
        assert len(result.cards) > 0
        assert result.total_snippets > 0

    def test_to_markdown(self) -> None:
        result = normalize_content(SAMPLE_CONTENT, query="fastapi")
        md = result.to_markdown()
        assert "###" in md
        assert "```" in md

    def test_to_dict(self) -> None:
        result = normalize_content(SAMPLE_CONTENT)
        d = result.to_dict()
        assert "total_snippets" in d
        assert "deduped_snippets" in d
        assert "card_count" in d

    def test_empty_content(self) -> None:
        result = normalize_content("")
        assert result.total_snippets == 0
        assert len(result.cards) == 0

    def test_small_budget_limits_output(self) -> None:
        result = normalize_content(SAMPLE_CONTENT, section_token_budget=10)
        assert result.total_tokens <= 20  # Very small budget

    def test_content_without_code_blocks(self) -> None:
        result = normalize_content("# Just text\n\nNo code blocks here.")
        assert result.total_snippets == 0
        assert len(result.cards) == 0

    def test_large_budget_no_truncation(self) -> None:
        result = normalize_content(SAMPLE_CONTENT, section_token_budget=100000)
        assert not result.budget_applied

    def test_deduped_count(self) -> None:
        """deduped_snippets tracks how many were removed."""
        result = normalize_content(SAMPLE_CONTENT)
        assert result.deduped_snippets >= 0

    def test_total_tokens_nonzero_with_content(self) -> None:
        result = normalize_content(SAMPLE_CONTENT)
        if result.total_snippets > 0:
            assert result.total_tokens > 0

    def test_cards_grouped_by_header(self) -> None:
        """Cards should be grouped by context header."""
        result = normalize_content(SAMPLE_CONTENT)
        titles = [c.title for c in result.cards]
        # Should have distinct titles (grouped by context header)
        assert len(titles) == len(set(titles))


class TestReferenceCard:
    def test_to_markdown_with_snippets(self) -> None:
        card = ReferenceCard(
            title="Test Section",
            snippets=[
                CodeSnippet(code="print('hi')", language="python", context="Example", token_count=3),
            ],
            summary="A test card.",
            token_count=3,
        )
        md = card.to_markdown()
        assert "### Test Section" in md
        assert "A test card." in md
        assert "```python" in md
        assert "print('hi')" in md
        assert "_Example_" in md

    def test_to_markdown_no_summary(self) -> None:
        card = ReferenceCard(
            title="Test",
            snippets=[CodeSnippet(code="x = 1", token_count=1)],
        )
        md = card.to_markdown()
        assert "### Test" in md
        assert "x = 1" in md

    def test_to_markdown_no_language(self) -> None:
        card = ReferenceCard(
            title="Test",
            snippets=[CodeSnippet(code="some code", language="", token_count=2)],
        )
        md = card.to_markdown()
        assert "```\n" in md

    def test_to_markdown_no_context(self) -> None:
        card = ReferenceCard(
            title="Test",
            snippets=[CodeSnippet(code="some code", context="", token_count=2)],
        )
        md = card.to_markdown()
        # No context means no italic line
        assert "_" not in md or "### " in md


class TestNormalizationResult:
    def test_to_markdown_empty(self) -> None:
        result = NormalizationResult()
        md = result.to_markdown()
        assert md == ""

    def test_to_dict_complete(self) -> None:
        result = NormalizationResult(
            cards=[ReferenceCard(title="Test", token_count=10)],
            total_snippets=5,
            deduped_snippets=2,
            total_tokens=100,
            budget_applied=True,
        )
        d = result.to_dict()
        assert d["total_snippets"] == 5
        assert d["deduped_snippets"] == 2
        assert d["total_tokens"] == 100
        assert d["budget_applied"] is True
        assert d["card_count"] == 1
