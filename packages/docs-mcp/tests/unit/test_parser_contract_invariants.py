"""Round-trip invariants for parsers of caller-supplied JSON arrays (TAP-5659).

One rule, enforced across every parser that accepts a structured array from a
tool caller:

    len(output) == len(input), or the call raises.

Never silently shorter. Both escaped defects behind TAP-5656 were the same
shape — ``if isinstance(item, dict)`` inside a loop, no ``else`` — so an
off-contract item vanished, the tool reported success, and the caller received
a document built from boilerplate. ``parse_stories_json`` and
``parse_phases_json`` each carried it independently, which is why the invariant
lives here as a shared parametrization rather than as two hand-written cases.

Scope note: parsers of *third-party tool output* (ruff, bandit, radon, semgrep,
pip-audit) are deliberately excluded. Skipping an unrecognised finding is
correct behaviour there — one odd entry must not fail an entire scan. The
invariant applies only where the array is a caller's contract input and a
dropped item silently changes the document the caller gets back.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from docs_mcp.generators.epics import EpicGenerator
from docs_mcp.generators.specs import PRDGenerator

# (label, parse callable, name-bearing attribute on each parsed item)
CALLER_INPUT_PARSERS: list[tuple[str, Callable[[str], list[Any]], str]] = [
    ("parse_stories_json", EpicGenerator.parse_stories_json, "title"),
    ("parse_phases_json", PRDGenerator.parse_phases_json, "name"),
]

PARSER_IDS = [label for label, _, _ in CALLER_INPUT_PARSERS]


@pytest.mark.parametrize(("label", "parse", "name_attr"), CALLER_INPUT_PARSERS, ids=PARSER_IDS)
class TestCallerInputParserInvariants:
    """Every item is honoured or refused — none are dropped."""

    def test_array_of_strings_is_honoured(
        self, label: str, parse: Callable[[str], list[Any]], name_attr: str
    ) -> None:
        titles = ["Phase 0: ratchet", "Phase 1: root causes", "Phase 2: sweep"]
        parsed = parse('["Phase 0: ratchet", "Phase 1: root causes", "Phase 2: sweep"]')

        assert len(parsed) == len(titles), f"{label} dropped items from an array of strings"
        assert [getattr(item, name_attr) for item in parsed] == titles

    def test_mixed_strings_and_objects_preserves_length(
        self, label: str, parse: Callable[[str], list[Any]], name_attr: str
    ) -> None:
        # The nastiest variant: the dicts survive and the strings vanish, so the
        # caller gets a plausible partial document with no signal at all.
        parsed = parse(f'[{{"{name_attr}": "From object"}}, "From string"]')

        assert len(parsed) == 2, f"{label} silently dropped the bare-string item"
        assert [getattr(item, name_attr) for item in parsed] == ["From object", "From string"]

    @pytest.mark.parametrize(
        "payload",
        ["[1, 2, 3]", "[null]", "[true]", "[[]]", '[["nested"]]', "[1.5]"],
        ids=["ints", "null", "bool", "empty-list", "nested-list", "float"],
    )
    def test_uninterpretable_items_raise_rather_than_drop(
        self, label: str, parse: Callable[[str], list[Any]], name_attr: str, payload: str
    ) -> None:
        with pytest.raises(ValueError):
            parse(payload)

    def test_empty_string_item_raises(
        self, label: str, parse: Callable[[str], list[Any]], name_attr: str
    ) -> None:
        with pytest.raises(ValueError):
            parse('["   "]')

    def test_blank_input_returns_empty(
        self, label: str, parse: Callable[[str], list[Any]], name_attr: str
    ) -> None:
        # Zero in, zero out still satisfies the invariant.
        assert parse("") == []
        assert parse("   ") == []

    def test_non_list_raises(
        self, label: str, parse: Callable[[str], list[Any]], name_attr: str
    ) -> None:
        with pytest.raises(ValueError):
            parse('{"not": "a list"}')

    def test_malformed_json_raises(
        self, label: str, parse: Callable[[str], list[Any]], name_attr: str
    ) -> None:
        with pytest.raises(ValueError):
            parse("[{unclosed")


class TestSuggestedStoriesAreDeclared:
    """A substituted body must announce itself (TAP-5657).

    story_count=0 beside a body of "(suggested)" placeholders gave the caller
    no way to connect the two. The response now says which it got.
    """

    @pytest.mark.asyncio
    async def test_supplied_stories_are_not_marked_suggested(self, tmp_path: Any) -> None:
        from docs_mcp.server_gen_planning import docs_generate_epic

        result = await docs_generate_epic(
            title="Real work",
            purpose_and_intent="We are doing this so that the parser contract holds.",
            goal="Honour caller-supplied stories.",
            motivation="Silent substitution misleads callers.",
            acceptance_criteria="Stories render verbatim",
            stories='["Phase 0: ratchet", "Phase 1: root causes"]',
            project_root=str(tmp_path),
        )
        data = result["data"]
        assert data["story_count"] == 2
        assert data["stories_suggested"] is False

    @pytest.mark.asyncio
    async def test_omitted_stories_are_marked_suggested(self, tmp_path: Any) -> None:
        from docs_mcp.server_gen_planning import docs_generate_epic

        result = await docs_generate_epic(
            title="CI pipeline deploy work",
            purpose_and_intent="We are doing this so that the fallback is visible.",
            goal="Expose the suggestion fallback.",
            motivation="Boilerplate must not masquerade as input.",
            acceptance_criteria="Fallback is declared",
            project_root=str(tmp_path),
        )
        data = result["data"]
        assert data["story_count"] == 0
        assert data["stories_suggested"] is True
