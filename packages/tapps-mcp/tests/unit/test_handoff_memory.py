"""Tests for handoff memory CLI enrichment (TAP-3794)."""

from __future__ import annotations

import json

from tapps_mcp.tools.handoff_memory import (
    enrich_memory_get_action_result,
    enrich_memory_get_entry,
    enrich_memory_save_action_result,
    enrich_memory_save_result,
)
from tapps_mcp.tools.handoff_schema import handoff_sections_from_doc, parse_handoff_markdown

_VALID = """\
# Session handoff
**Updated:** 2026-06-12T12:00:00Z
**Linear P0:** TAP-3790

## Done
- item one

## Open
- none

## Next (P0)
- next action

## Blockers
- none

## Verify
- uv run pytest

## Success criterion
- pass
"""


class TestHandoffMemoryEnrichment:
    def test_sections_from_doc(self) -> None:
        doc = parse_handoff_markdown(_VALID)
        sections = handoff_sections_from_doc(doc)
        assert sections["linear_p0"] == "TAP-3790"
        assert sections["done"] == ["item one"]
        assert sections["next_p0"] == ["next action"]

    def test_get_strips_embedding_and_adds_sections(self) -> None:
        entry = {
            "key": "session-handoff",
            "value": _VALID,
            "embedding": [0.1, 0.2, 0.3],
            "confidence": 0.6,
        }
        out = enrich_memory_get_entry("session-handoff", entry)
        assert "embedding" not in out
        assert out["handoff_sections"]["next_p0"] == ["next action"]

    def test_get_parses_details_json_metadata(self) -> None:
        meta = {"git_sha": "abc1234", "handoff_sections": {"linear_p0": "TAP-1"}}
        entry = {
            "key": "session-handoff",
            "value": _VALID,
            "details_json": json.dumps(meta),
        }
        out = enrich_memory_get_entry("session-handoff", entry)
        assert out["handoff_metadata"]["git_sha"] == "abc1234"

    def test_get_other_keys_unchanged_except_embedding_strip(self) -> None:
        entry = {"key": "arch-decision", "value": "x", "embedding_vector": [1.0]}
        out = enrich_memory_get_entry("arch-decision", entry)
        assert "embedding_vector" not in out
        assert "handoff_sections" not in out

    def test_save_adds_memory_group_note(self) -> None:
        out = enrich_memory_save_result({"key": "x", "success": True, "memory_group": None})
        assert "memory_group_note" in out

    def test_save_skips_note_when_group_set(self) -> None:
        out = enrich_memory_save_result({"key": "x", "memory_group": "insights"})
        assert "memory_group_note" not in out

    def test_get_action_result_enriches_entry(self) -> None:
        payload = enrich_memory_get_action_result(
            "session-handoff",
            {
                "action": "get",
                "found": True,
                "entry": {"key": "session-handoff", "value": _VALID, "embedding": [1.0]},
            },
        )
        assert "embedding" not in payload["entry"]
        assert payload["entry"]["handoff_sections"]["linear_p0"] == "TAP-3790"

    def test_save_action_result_enriches_entry(self) -> None:
        payload = enrich_memory_save_action_result(
            {"action": "save", "entry": {"key": "x", "memory_group": None}}
        )
        assert "memory_group_note" in payload["entry"]
