"""Tests for handoff memory CLI enrichment (TAP-3794)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tapps_mcp.tools.handoff_memory import (
    enrich_memory_get_action_result,
    enrich_memory_get_entry,
    enrich_memory_save_action_result,
    enrich_memory_save_result,
)
from tapps_mcp.tools.handoff_schema import (
    handoff_memory_key,
    handoff_sections_from_doc,
    parse_handoff_markdown,
)

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
        key = handoff_memory_key()
        entry = {
            "key": key,
            "value": _VALID,
            "embedding": [0.1, 0.2, 0.3],
            "confidence": 0.6,
        }
        out = enrich_memory_get_entry(key, entry)
        assert "embedding" not in out
        assert out["handoff_sections"]["next_p0"] == ["next action"]

    def test_get_parses_details_json_metadata(self) -> None:
        key = handoff_memory_key()
        meta = {"git_sha": "abc1234", "handoff_sections": {"linear_p0": "TAP-1"}}
        entry = {
            "key": key,
            "value": _VALID,
            "details_json": json.dumps(meta),
        }
        out = enrich_memory_get_entry(key, entry)
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
        key = handoff_memory_key()
        payload = enrich_memory_get_action_result(
            key,
            {
                "action": "get",
                "found": True,
                "entry": {"key": key, "value": _VALID, "embedding": [1.0]},
            },
        )
        assert "embedding" not in payload["entry"]
        assert payload["entry"]["handoff_sections"]["linear_p0"] == "TAP-3790"

    def test_save_action_result_enriches_entry(self) -> None:
        payload = enrich_memory_save_action_result(
            {"action": "save", "entry": {"key": "x", "memory_group": None}}
        )
        assert "memory_group_note" in payload["entry"]


class TestSlottedKeysKeepTheirEnrichment:
    """TAP-6873: a slotted key must not lose enrichment to a key equality.

    ``enrich_memory_get_entry`` gated on ``key == SESSION_HANDOFF_MEMORY_KEY``,
    so every slotted handoff silently came back without ``handoff_sections`` or
    ``handoff_metadata`` — the two fields continue-session reads.
    """

    _META = {"git_sha": "abc1234"}

    def _entry(self, key: str) -> dict[str, Any]:
        return {"key": key, "value": _VALID, "details_json": json.dumps(self._META)}

    def test_slotted_key_is_recognized(self) -> None:
        key = handoff_memory_key("ceg-hub")
        out = enrich_memory_get_entry(key, self._entry(key))
        assert out["handoff_sections"]["next_p0"] == ["next action"]
        assert out["handoff_metadata"]["git_sha"] == "abc1234"

    def test_default_key_still_recognized(self) -> None:
        key = handoff_memory_key()
        out = enrich_memory_get_entry(key, self._entry(key))
        assert out["handoff_sections"]["next_p0"] == ["next action"]

    def test_action_result_enriches_a_slotted_entry(self) -> None:
        key = handoff_memory_key("ceg-hub")
        payload = enrich_memory_get_action_result(
            key, {"action": "get", "found": True, "entry": self._entry(key)}
        )
        assert payload["entry"]["handoff_sections"]["linear_p0"] == "TAP-3790"

    @pytest.mark.parametrize(
        "key",
        [
            "session-handoffs",  # prefix without the dot separator
            "session-handoff-ceg-hub",  # the dash form the dot replaced
            "not-session-handoff.ceg-hub",  # the prefix must anchor at the start
            "arch-decision",
        ],
    )
    def test_neighbouring_keys_are_not_enriched(self, key: str) -> None:
        """Negative control: the predicate is a prefix match, not a substring one."""
        out = enrich_memory_get_entry(key, self._entry(key))
        assert "handoff_sections" not in out
        assert "handoff_metadata" not in out
