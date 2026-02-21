"""Unit tests for tapps_mcp.knowledge.content_normalizer."""

from __future__ import annotations

from tapps_mcp.knowledge.content_normalizer import (
    CodeSnippet,
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
