"""The tapps_memory migration doc must not claim the tool was removed.

TAP-3895 / ADR-0016 restored `tapps_memory` as a supported slim facade on the
`nlt-memory` profile (commit 7486cc34, 2026-06-13). The migration doc drifted
and kept saying "REMOVED" / "no longer registered in any server preset" for
months after that. This test asserts the doc no longer carries those retired
claims, and derives the "tapps_memory is registered" fact from the actual
profile table rather than restating it.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.server import TOOL_PROFILE_NLT_MEMORY

_DOC_PATH = (
    Path(__file__).resolve().parents[4] / "docs" / "migrations" / "tapps-memory-deprecation.md"
)

_RETIRED_PHRASES = (
    "no longer registered in any server preset",
    "Status:** REMOVED",
)


def test_migration_doc_does_not_claim_tool_removed() -> None:
    text = _DOC_PATH.read_text(encoding="utf-8")
    for phrase in _RETIRED_PHRASES:
        assert phrase not in text, f"migration doc still claims a retired state: {phrase!r}"


def test_tapps_memory_is_registered_on_nlt_memory_profile() -> None:
    assert "tapps_memory" in TOOL_PROFILE_NLT_MEMORY
