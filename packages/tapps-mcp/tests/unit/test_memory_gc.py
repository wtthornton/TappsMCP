"""Tests for memory garbage collection (Epic 24.4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tapps_mcp.memory.decay import DecayConfig
from tapps_mcp.memory.gc import GCResult, MemoryGarbageCollector
from tapps_mcp.memory.models import MemoryEntry, MemoryScope, MemorySource, MemoryTier


def _make_entry(
    *,
    key: str = "test-key",
    tier: MemoryTier = MemoryTier.pattern,
    confidence: float = 0.8,
    updated_at: str | None = None,
    scope: MemoryScope = MemoryScope.project,
    contradicted: bool = False,
) -> MemoryEntry:
    """Helper to create a MemoryEntry with controlled state."""
    now_iso = datetime.now(tz=UTC).isoformat()
    entry = MemoryEntry(
        key=key,
        value="test value",
        tier=tier,
        source=MemorySource.agent,
        confidence=confidence,
        updated_at=updated_at or now_iso,
        created_at=now_iso,
        last_accessed=now_iso,
        scope=scope,
    )
    if contradicted:
        object.__setattr__(entry, "contradicted", True)
        object.__setattr__(entry, "contradiction_reason", "test")
    return entry


@pytest.fixture
def config() -> DecayConfig:
    return DecayConfig()


@pytest.fixture
def gc(config: DecayConfig) -> MemoryGarbageCollector:
    return MemoryGarbageCollector(config)


class TestIdentifyCandidates:
    def test_deeply_decayed_memory_archived(self, gc: MemoryGarbageCollector) -> None:
        """Memory at confidence floor for 30+ days gets archived."""
        now = datetime.now(tz=UTC)
        # Pattern half-life is 60 days. At ~600 days, confidence is deeply floored.
        old_update = (now - timedelta(days=600)).isoformat()
        entry = _make_entry(confidence=0.8, updated_at=old_update)

        candidates = gc.identify_candidates([entry], now=now)
        assert len(candidates) == 1
        assert candidates[0].key == "test-key"

    def test_contradicted_low_confidence_archived(self, gc: MemoryGarbageCollector) -> None:
        """Contradicted memory with low effective confidence gets archived."""
        now = datetime.now(tz=UTC)
        # Make it old enough that effective confidence < 0.2
        old_update = (now - timedelta(days=180)).isoformat()
        entry = _make_entry(confidence=0.5, updated_at=old_update, contradicted=True)

        candidates = gc.identify_candidates([entry], now=now)
        assert len(candidates) == 1

    def test_above_threshold_survives(self, gc: MemoryGarbageCollector) -> None:
        """A reasonably fresh memory is NOT a GC candidate."""
        now = datetime.now(tz=UTC)
        entry = _make_entry(confidence=0.8)

        candidates = gc.identify_candidates([entry], now=now)
        assert len(candidates) == 0

    def test_session_scoped_expired(self, gc: MemoryGarbageCollector) -> None:
        """Session-scoped memory older than 7 days gets archived."""
        now = datetime.now(tz=UTC)
        old_update = (now - timedelta(days=10)).isoformat()
        entry = _make_entry(scope=MemoryScope.session, updated_at=old_update)

        candidates = gc.identify_candidates([entry], now=now)
        assert len(candidates) == 1

    def test_session_scoped_fresh_survives(self, gc: MemoryGarbageCollector) -> None:
        """Recent session-scoped memory is NOT archived."""
        now = datetime.now(tz=UTC)
        entry = _make_entry(scope=MemoryScope.session)

        candidates = gc.identify_candidates([entry], now=now)
        assert len(candidates) == 0


# TAP-5404: `TestAppendToArchive` removed. tapps-brain 3.28.0 deleted
# `MemoryGarbageCollector.append_to_archive` along with file-based JSONL
# archiving — archiving now happens in `PostgresPrivateBackend.archive_entry`
# and `archived_at` is a column rather than part of the payload. The only
# module-level survivor is `archive_entries_jsonl_utf8_bytes`, a dry-run byte
# estimator with a different contract. The old tests asserted a JSONL file
# with an in-payload `archived_at`, which no longer exists anywhere; no
# tapps-mcp production code ever called the removed API.


class TestGCResult:
    def test_default_values(self) -> None:
        result = GCResult()
        assert result.archived_count == 0
        assert result.remaining_count == 0
        assert result.archived_keys == []
