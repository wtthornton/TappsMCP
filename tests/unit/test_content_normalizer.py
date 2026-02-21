"""Unit tests for tapps_mcp.knowledge.content_normalizer."""

from __future__ import annotations

import pytest

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
        assert len(snippets) >= 2

    def test_captures_language_and_context(self) -> None:
        snippets = extract_snippets(SAMPLE_CONTENT)
        languages = {s.language for s in snippets}
        assert "python" in languages
        python_snippets = [s for s in snippets if s.language == "python"]
        assert any("Basic Example" in s.context or "Advanced" in s.context for s in python_snippets)

    def test_token_count_set(self) -> None:
        for s in extract_snippets(SAMPLE_CONTENT):
            assert s.token_count > 0

    @pytest.mark.parametrize("length,expected_count", [
        (30, 1),   # exactly at MIN_SNIPPET_LENGTH
        (29, 0),   # just below
    ], ids=["at-min", "below-min"])
    def test_snippet_length_boundary(self, length, expected_count) -> None:
        content = f"```python\n{'a' * length}\n```"
        assert len(extract_snippets(content)) == expected_count

    def test_no_language_specified(self) -> None:
        snippets = extract_snippets("## Section\n\n```\nsome long content that is at least 30 chars\n```")
        assert len(snippets) == 1 and snippets[0].language == ""

    def test_content_with_no_code_blocks(self) -> None:
        assert extract_snippets("# Just text\nNo code blocks.") == []

    def test_content_with_no_headers(self) -> None:
        snippets = extract_snippets("Text.\n\n```python\ndef foo():\n    return 'bar' * 100\n```")
        assert len(snippets) == 1

    def test_multiple_headers_picks_nearest(self) -> None:
        content = "# First\n\nText.\n\n## Second\n\n```python\ndef foo():\n    return 'test' * 100\n```"
        snippets = extract_snippets(content)
        assert len(snippets) == 1 and "Second" in snippets[0].context


class TestRankSnippets:
    def test_ranks_by_completeness(self) -> None:
        snippets = [
            CodeSnippet(code="x = 1", token_count=2),
            CodeSnippet(code="from fastapi import FastAPI\ndef main():\n    return 'ok'", token_count=15),
        ]
        ranked = rank_snippets(snippets)
        assert ranked[0].code.startswith("from fastapi")

    def test_query_relevance_boosts(self) -> None:
        snippets = [
            CodeSnippet(code="print('hello world')\nreturn 1", language="python", token_count=5),
            CodeSnippet(code="def test_sql_injection():\n    query = 'SELECT * FROM users'\n    return query", language="python", token_count=10),
        ]
        ranked = rank_snippets(snippets, query="sql injection")
        assert "sql" in ranked[0].code.lower()

    def test_empty_and_stopword_queries(self) -> None:
        """Empty and stopword-only queries don't crash."""
        snip = CodeSnippet(code="from fastapi import FastAPI\ndef main():\n    return 'ok'", token_count=10)
        assert len(rank_snippets([snip], query="")) == 1
        assert len(rank_snippets([snip], query="how to the a in")) == 1

    def test_language_preference(self) -> None:
        py = CodeSnippet(code="x = 1\ny = 2\nz = 3", language="python", token_count=5)
        sh = CodeSnippet(code="x = 1\ny = 2\nz = 3", language="bash", token_count=5)
        rank_snippets([py, sh])
        assert py.score > sh.score

    def test_scores_clamped(self) -> None:
        snip = CodeSnippet(code="from x import y\ndef f():\n    class C:\n        return 1", language="python", token_count=15)
        rank_snippets([snip], query="x y f C return")
        assert 0.0 <= snip.score <= 1.0

    def test_no_signals_score_zero(self) -> None:
        snip = CodeSnippet(code="some plain text without keywords here now", language="rust", token_count=5)
        rank_snippets([snip])
        assert snip.score == 0.0


class TestDeduplicateSnippets:
    def test_removes_exact_duplicates(self) -> None:
        s = CodeSnippet(code="from fastapi import FastAPI", token_count=5)
        assert len(deduplicate_snippets([s, s])) == 1

    def test_removes_substring_duplicates(self) -> None:
        short = CodeSnippet(code="import fastapi", token_count=3)
        long = CodeSnippet(code="import fastapi\napp = FastAPI()\nreturn app", token_count=8)
        assert len(deduplicate_snippets([long, short])) == 1

    def test_keeps_different_snippets(self) -> None:
        a = CodeSnippet(code="from flask import Flask\napp = Flask(__name__)", token_count=8)
        b = CodeSnippet(code="import pytest\ndef test_func():\n    assert True", token_count=8)
        assert len(deduplicate_snippets([a, b])) == 2

    @pytest.mark.parametrize("input_list,expected_len", [
        ([], 0),
        ("single", 1),
        ("triple", 1),
    ], ids=["empty", "single", "all-identical"])
    def test_dedup_edge_cases(self, input_list, expected_len) -> None:
        if input_list == []:
            assert deduplicate_snippets([]) == []
        elif input_list == "single":
            s = CodeSnippet(code="print('hello')", token_count=3)
            assert len(deduplicate_snippets([s])) == 1
        else:
            s = CodeSnippet(code="from os import path\nresult = path.join('a', 'b')", token_count=5)
            assert len(deduplicate_snippets([s, s, s])) == 1

    def test_custom_threshold_relaxes_dedup(self) -> None:
        a = CodeSnippet(code="from fastapi import FastAPI\napp = FastAPI()", token_count=5)
        b = CodeSnippet(code="from fastapi import FastAPI\napi = FastAPI()", token_count=5)
        # threshold=1.0 means only exact duplicates are removed
        assert len(deduplicate_snippets([a, b], threshold=1.0)) == 2


class TestApplyTokenBudget:
    @pytest.mark.parametrize("token_count,budget,expected_len", [
        (100, 200, 2),     # fits 2 of 3
        (50, 0, 0),        # zero budget
        (100, 100, 1),     # exactly at budget
        (101, 100, 0),     # one over budget
        (50, 1000, 2),     # budget larger than total
    ], ids=["fits-two", "zero-budget", "at-budget", "over-budget", "large-budget"])
    def test_budget_enforcement(self, token_count, budget, expected_len) -> None:
        if token_count == 100 and budget == 200:
            snippets = [CodeSnippet(code="x" * 100, token_count=100) for _ in range(3)]
        elif token_count == 50 and budget == 1000:
            snippets = [CodeSnippet(code="x" * 50, token_count=50) for _ in range(2)]
        else:
            snippets = [CodeSnippet(code="x" * token_count, token_count=token_count)]
        assert len(apply_token_budget(snippets, budget=budget)) == expected_len

    def test_empty_snippets(self) -> None:
        assert apply_token_budget([], budget=100) == []

    def test_preserves_order(self) -> None:
        snippets = [CodeSnippet(code=f"item{i}", token_count=10) for i in range(3)]
        result = apply_token_budget(snippets, budget=25)
        assert [r.code for r in result] == ["item0", "item1"]


class TestNormalizeContent:
    def test_produces_reference_cards(self) -> None:
        result = normalize_content(SAMPLE_CONTENT, query="fastapi endpoint")
        assert len(result.cards) > 0 and result.total_snippets > 0

    def test_output_formats(self) -> None:
        """to_markdown and to_dict both produce correct output."""
        result = normalize_content(SAMPLE_CONTENT, query="fastapi")
        md = result.to_markdown()
        assert "###" in md and "```" in md
        d = result.to_dict()
        assert all(k in d for k in ("total_snippets", "deduped_snippets", "card_count"))

    def test_empty_content(self) -> None:
        result = normalize_content("")
        assert result.total_snippets == 0 and len(result.cards) == 0

    def test_no_code_blocks(self) -> None:
        result = normalize_content("# Just text\nNo code blocks here.")
        assert result.total_snippets == 0 and len(result.cards) == 0

    def test_small_budget_limits_output(self) -> None:
        result = normalize_content(SAMPLE_CONTENT, section_token_budget=10)
        assert result.total_tokens <= 20

    def test_large_budget_no_truncation(self) -> None:
        assert not normalize_content(SAMPLE_CONTENT, section_token_budget=100000).budget_applied

    def test_cards_grouped_by_header(self) -> None:
        result = normalize_content(SAMPLE_CONTENT)
        titles = [c.title for c in result.cards]
        assert len(titles) == len(set(titles))


class TestReferenceCard:
    def test_to_markdown_with_all_fields(self) -> None:
        card = ReferenceCard(
            title="Test Section",
            snippets=[CodeSnippet(code="print('hi')", language="python", context="Example", token_count=3)],
            summary="A test card.",
            token_count=3,
        )
        md = card.to_markdown()
        assert "### Test Section" in md
        assert "A test card." in md
        assert "```python" in md
        assert "_Example_" in md

    def test_to_markdown_no_language_or_context(self) -> None:
        card = ReferenceCard(
            title="Test",
            snippets=[CodeSnippet(code="some code", language="", context="", token_count=2)],
        )
        md = card.to_markdown()
        assert "```\n" in md


class TestNormalizationResult:
    def test_empty_to_markdown(self) -> None:
        assert NormalizationResult().to_markdown() == ""

    def test_to_dict_complete(self) -> None:
        result = NormalizationResult(
            cards=[ReferenceCard(title="Test", token_count=10)],
            total_snippets=5, deduped_snippets=2, total_tokens=100, budget_applied=True,
        )
        d = result.to_dict()
        assert d == {"total_snippets": 5, "deduped_snippets": 2, "total_tokens": 100,
                     "budget_applied": True, "card_count": 1}
