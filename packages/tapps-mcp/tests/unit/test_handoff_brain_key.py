"""The slotted handoff brain key, proved against a real ``save`` (TAP-6873).

The brain validates ``MemoryEntry.key`` against ``_KEY_SLUG_PATTERN`` on the
**server** side; nothing in ``handoff_schema`` pre-checks a key. A test that
asserts only the string ``handoff_memory_key`` returns is therefore green on a
key every production write rejects — which is exactly what the colon form was.
So every claim here goes through a real ``MemoryStore.save``:

* the dot form is **accepted** and reads back, and enrichment on the stored row
  returns ``handoff_sections`` and ``handoff_metadata``;
* the colon form is **rejected** by that same validator — the negative control
  that shows the save reaches it at all.

The store is the ``InMemoryPrivateBackend`` the autouse conftest fixture injects
(no Postgres, no live brain). The backend is a storage layer only: the key
validator lives on the Pydantic model, so it runs here exactly as it does in
production. ``tests/unit/test_handoff_slots.py`` pins the returned strings; this
file pins that the brain will take them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tapps_core.brain_bridge import BrainBridge, BrainBridgeUnavailable
from tapps_mcp.tools.handoff_memory import enrich_memory_get_entry
from tapps_mcp.tools.handoff_schema import handoff_memory_key, parse_handoff_markdown
from tapps_mcp.tools.handoff_write import build_handoff_metadata

_SLOT = "ceg-hub"

# The key the spec corrected away from. Written out rather than derived, because
# the point of the control is that the naming site can no longer produce it.
_COLON_KEY = f"session-handoff:{_SLOT}"

_HANDOFF = """\
# Session handoff
**Program:** ceg-hub
**Updated:** 2026-09-01T12:00:00Z
**Linear P0:** TAP-6873

## Done
- landed the dot-separated key

## Open
- none

## Next (P0)
- wire the surfaces

## Success criterion
- a real save accepts the slotted key
"""


class _BrainHolder:
    """The one attribute ``BrainBridge`` reaches for on an in-process brain.

    Constructing a full ``AgentBrain`` loads the real embedding model, which
    costs seconds and a network fetch; the bridge only ever touches ``.store``.
    """

    def __init__(self, store: Any) -> None:
        self.store = store


@pytest.fixture()
def bridge(tmp_path: Path) -> BrainBridge:
    from tapps_brain.store import MemoryStore

    return BrainBridge(_BrainHolder(MemoryStore(tmp_path)))


@pytest.mark.live_network
class TestTheSlottedKeyIsWritable:
    """TAP-6592: the ``bridge`` fixture's ``MemoryStore`` is a real, pinned
    tapps-brain instance whose own default embeds saved content via
    sentence-transformers, downloading its model from HuggingFace Hub on a
    cache miss -- out of this repo's boundary to fix. Marked live_network
    rather than silently broken by the new root guard.
    """

    async def test_dot_form_is_accepted_by_a_real_save(self, bridge: BrainBridge) -> None:
        key = handoff_memory_key(_SLOT)
        assert key == "session-handoff.ceg-hub"

        saved = await bridge.save(key, _HANDOFF, tier="context", tags=["handoff"])

        assert saved["key"] == key
        assert saved["value"] == _HANDOFF

    async def test_colon_form_is_rejected_by_the_same_validator(self, bridge: BrainBridge) -> None:
        """Negative control: without it, acceptance above proves nothing.

        A save that never reached the validator would accept both forms. This
        one is refused, and the message is the brain's own slug rule — so the
        positive case is a verdict from the validator, not from a stub.
        """
        with pytest.raises(BrainBridgeUnavailable) as exc_info:
            await bridge.save(_COLON_KEY, _HANDOFF, tier="context")

        message = str(exc_info.value)
        assert "validation error for MemoryEntry" in message
        assert "Key must be a lowercase slug" in message
        assert _COLON_KEY in message

    async def test_the_naming_site_can_no_longer_produce_the_colon_form(self) -> None:
        assert handoff_memory_key(_SLOT) != _COLON_KEY

    async def test_the_slotted_key_reverse_parses_to_its_slot(self) -> None:
        """The dot is unambiguous: the slot allowlist forbids dots."""
        prefix, slot = handoff_memory_key(_SLOT).split(".", 1)
        assert (prefix, slot) == (handoff_memory_key(), _SLOT)


@pytest.mark.live_network
class TestEnrichmentSurvivesTheSlot:
    """TAP-6592: see TestTheSlottedKeyIsWritable's docstring -- same real,
    pinned ``bridge``/``MemoryStore`` fixture.
    """

    async def test_stored_slotted_row_enriches_with_sections_and_metadata(
        self, bridge: BrainBridge
    ) -> None:
        """Both enrichment branches fire for a key that came back from a save.

        What this brackets is the **read side**: given a row whose key is
        slotted, ``enrich_memory_get_entry`` attaches ``handoff_sections`` from
        the stored value and ``handoff_metadata`` from ``details_json``. The key
        is the one a real save accepted above; only the ``details_json`` field
        is set here by hand.

        It has to be set by hand, because no brain at the pinned floor
        (``>=3.28.0,<4``) persists it: ``details_json`` is neither a
        ``MemoryEntry`` field nor a parameter of ``MemoryStore.save`` or of the
        brain's ``memory_save`` MCP tool — it belongs to
        ``brain_record_feedback``. The mirror therefore no longer sends it
        (TAP-6874); handoff metadata travels in the tool response instead. So
        the ``handoff_metadata`` branch asserted here is a contract for any
        caller that *does* hold such a row, not a claim that the mirror writes
        one. The value is still not invented — it is exactly what
        ``build_handoff_metadata`` composes for this document.
        """
        key = handoff_memory_key(_SLOT)
        await bridge.save(key, _HANDOFF, tier="context", tags=["handoff"])

        row = await bridge.get(key)
        assert row is not None
        metadata = build_handoff_metadata(parse_handoff_markdown(_HANDOFF), {"git_sha": "abc1234"})
        row["details_json"] = json.dumps(metadata)

        enriched = enrich_memory_get_entry(key, row)

        assert enriched["handoff_sections"]["next_p0"] == ["wire the surfaces"]
        assert enriched["handoff_sections"]["linear_p0"] == "TAP-6873"
        assert enriched["handoff_metadata"]["git_sha"] == "abc1234"


class TestTheRejectionSurfacesAsBrainValidationFailed:
    """How the refusal above reaches an agent when it happens over HTTP.

    The in-process bridge raises; the HTTP bridge returns the brain's error
    payload, and ``_classify_http_bridge_result`` is what turns that into the
    ``brain_validation_failed`` code rather than a ``success: true`` with the
    failure buried under ``data.entry``. The message fed in is the real
    validator's, raised by constructing the model this test does not stub.
    """

    @staticmethod
    def _real_rejection_message() -> str:
        from tapps_brain.models import MemoryEntry

        with pytest.raises(ValueError) as exc_info:
            MemoryEntry(key=_COLON_KEY, value=_HANDOFF)
        return str(exc_info.value)

    # ``_classify_http_bridge_result`` is deliberately value-agnostic — it asks
    # ``if err:``, and its own docstring names ``invalid_source`` as the shape it
    # was written for. Pinning one literal let a narrowing to
    # ``if err == "validation_error":`` stay green while every other brain error
    # came back as ``success: true`` with the failure buried under ``data.entry``
    # (TAP-6874, refuter survivor M7). More than one real value is what makes
    # that mutation impossible.
    _BRAIN_ERROR_CODES = ("validation_error", "invalid_source", "rate_limited")

    @pytest.mark.parametrize("brain_error", _BRAIN_ERROR_CODES)
    def test_a_brain_error_is_classified_brain_validation_failed(self, brain_error: str) -> None:
        from tapps_mcp.server_memory_tools import _classify_http_bridge_result

        message = self._real_rejection_message()
        assert "Key must be a lowercase slug" in message

        classified = _classify_http_bridge_result(
            "save", {"entry": {"error": brain_error, "message": message}}
        )

        assert classified is not None
        assert classified["error"]["code"] == "brain_validation_failed"
        assert classified["error"]["brain_error"] == brain_error
        assert "Key must be a lowercase slug" in classified["error"]["message"]

    def test_an_accepted_save_is_not_classified_as_a_failure(self) -> None:
        """Negative control for the classifier: a healthy row passes through."""
        from tapps_mcp.server_memory_tools import _classify_http_bridge_result

        healthy = {"entry": {"key": handoff_memory_key(_SLOT), "value": _HANDOFF}}
        assert _classify_http_bridge_result("save", healthy) is None
