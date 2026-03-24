"""Unit tests for knowledge freshness warnings in expert consultations (Epic 35.3).

Tests the freshness checking logic in engine._check_freshness, the new
ConsultationResult fields, and the stale-knowledge nudge.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from tapps_core.experts.engine import (
    _check_freshness,
    _FreshnessResult,
    _KnowledgeResult,
)
from tapps_core.experts.models import ConsultationResult, KnowledgeChunk


class TestCheckFreshnessNoChunks:
    """When no chunks are retrieved, freshness check should be a no-op."""

    def test_no_chunks_returns_default(self, tmp_path: Path) -> None:
        knowledge = _KnowledgeResult(chunks=[], context="", sources=[])
        result = _check_freshness(knowledge, tmp_path)
        assert result.stale_knowledge is False
        assert result.oldest_chunk_age_days is None
        assert result.freshness_caveat is None


class TestCheckFreshnessFreshKnowledge:
    """When knowledge files are recent (< 365 days), no caveat."""

    def test_fresh_files_no_caveat(self, tmp_path: Path) -> None:
        # Create a fresh knowledge file.
        kb_file = tmp_path / "fresh-topic.md"
        kb_file.write_text("# Fresh knowledge\nSome content here.")

        chunks = [
            KnowledgeChunk(
                content="Some content here.",
                source_file="fresh-topic.md",
                line_start=1,
                line_end=2,
                score=0.9,
            ),
        ]
        knowledge = _KnowledgeResult(
            chunks=chunks, context="Some content", sources=["fresh-topic.md"]
        )

        result = _check_freshness(knowledge, tmp_path)
        assert result.stale_knowledge is False
        assert result.freshness_caveat is None
        assert result.oldest_chunk_age_days is not None
        assert result.oldest_chunk_age_days < 365


class TestCheckFreshnessStaleKnowledge:
    """When all top chunks come from files > 365 days old, mark as stale."""

    def test_stale_files_produce_caveat(self, tmp_path: Path) -> None:
        # Create a knowledge file and backdate it.
        kb_file = tmp_path / "old-topic.md"
        kb_file.write_text("# Old knowledge\nOutdated content.")

        # Set mtime to 400 days ago.
        old_time = time.time() - (400 * 86400)
        os.utime(kb_file, (old_time, old_time))

        chunks = [
            KnowledgeChunk(
                content="Outdated content.",
                source_file="old-topic.md",
                line_start=1,
                line_end=2,
                score=0.8,
            ),
        ]
        knowledge = _KnowledgeResult(
            chunks=chunks, context="Outdated content", sources=["old-topic.md"]
        )

        result = _check_freshness(knowledge, tmp_path)
        assert result.stale_knowledge is True
        assert result.oldest_chunk_age_days is not None
        assert result.oldest_chunk_age_days >= 400
        assert result.freshness_caveat is not None
        assert "tapps_lookup_docs()" in result.freshness_caveat
        assert "outdated" in result.freshness_caveat


class TestCheckFreshnessMixedAge:
    """When some chunks are fresh and some are stale, uses oldest age but not stale."""

    def test_mixed_freshness_not_stale(self, tmp_path: Path) -> None:
        # Create one fresh and one stale file.
        fresh_file = tmp_path / "fresh.md"
        fresh_file.write_text("Fresh content.")

        stale_file = tmp_path / "stale.md"
        stale_file.write_text("Stale content.")
        old_time = time.time() - (400 * 86400)
        os.utime(stale_file, (old_time, old_time))

        chunks = [
            KnowledgeChunk(
                content="Fresh content.",
                source_file="fresh.md",
                line_start=1,
                line_end=1,
                score=0.9,
            ),
            KnowledgeChunk(
                content="Stale content.",
                source_file="stale.md",
                line_start=1,
                line_end=1,
                score=0.7,
            ),
        ]
        knowledge = _KnowledgeResult(
            chunks=chunks, context="Content", sources=["fresh.md", "stale.md"]
        )

        result = _check_freshness(knowledge, tmp_path)
        assert result.stale_knowledge is False
        assert result.oldest_chunk_age_days is not None
        assert result.oldest_chunk_age_days >= 400
        assert result.freshness_caveat is None


class TestCheckFreshnessMultipleStaleFiles:
    """When all top 3 chunks are stale, result is stale."""

    def test_all_three_stale(self, tmp_path: Path) -> None:
        old_time = time.time() - (500 * 86400)
        files = ["a.md", "b.md", "c.md"]
        for name in files:
            f = tmp_path / name
            f.write_text(f"Content of {name}")
            os.utime(f, (old_time, old_time))

        chunks = [
            KnowledgeChunk(
                content=f"Content of {name}",
                source_file=name,
                line_start=1,
                line_end=1,
                score=0.8,
            )
            for name in files
        ]
        knowledge = _KnowledgeResult(
            chunks=chunks, context="Content", sources=files
        )

        result = _check_freshness(knowledge, tmp_path)
        assert result.stale_knowledge is True
        assert result.oldest_chunk_age_days is not None
        assert result.oldest_chunk_age_days >= 500
        assert result.freshness_caveat is not None


class TestCheckFreshnessFrontmatterLastReviewed:
    """last_reviewed in YAML frontmatter participates in effective file age."""

    def test_old_last_reviewed_makes_stale_despite_fresh_mtime(self, tmp_path: Path) -> None:
        kb_file = tmp_path / "review-stale.md"
        kb_file.write_text(
            "---\nlast_reviewed: 2020-01-01\n---\n\n# Topic\nBody.\n",
            encoding="utf-8",
        )

        chunks = [
            KnowledgeChunk(
                content="Body.",
                source_file="review-stale.md",
                line_start=1,
                line_end=5,
                score=0.9,
            ),
        ]
        knowledge = _KnowledgeResult(
            chunks=chunks, context="Body.", sources=["review-stale.md"]
        )

        result = _check_freshness(knowledge, tmp_path)
        assert result.stale_knowledge is True
        assert result.oldest_chunk_age_days is not None
        assert result.oldest_chunk_age_days >= 365
        assert result.freshness_caveat is not None

    def test_last_reviewed_combined_with_mtime_uses_max_age(self, tmp_path: Path) -> None:
        """Effective age is max(mtime, review); both must be under threshold to be fresh."""
        reviewed = (datetime.now(tz=UTC) - timedelta(days=60)).date().isoformat()
        kb_file = tmp_path / "both-reasonably-fresh.md"
        kb_file.write_text(
            f"---\nlast_reviewed: {reviewed}\n---\n\n# Topic\nBody.\n",
            encoding="utf-8",
        )
        medium_time = time.time() - (10 * 86400)
        os.utime(kb_file, (medium_time, medium_time))

        chunks = [
            KnowledgeChunk(
                content="Body.",
                source_file="both-reasonably-fresh.md",
                line_start=1,
                line_end=5,
                score=0.85,
            ),
        ]
        knowledge = _KnowledgeResult(
            chunks=chunks,
            context="Body.",
            sources=["both-reasonably-fresh.md"],
        )

        result = _check_freshness(knowledge, tmp_path)
        assert result.stale_knowledge is False
        assert result.freshness_caveat is None
        assert result.oldest_chunk_age_days is not None
        assert 58 <= result.oldest_chunk_age_days <= 62


class TestCheckFreshnessMissingFile:
    """When source file doesn't exist on disk, skip it gracefully."""

    def test_missing_file_skipped(self, tmp_path: Path) -> None:
        chunks = [
            KnowledgeChunk(
                content="Content from missing file.",
                source_file="nonexistent.md",
                line_start=1,
                line_end=1,
                score=0.8,
            ),
        ]
        knowledge = _KnowledgeResult(
            chunks=chunks, context="Content", sources=["nonexistent.md"]
        )

        result = _check_freshness(knowledge, tmp_path)
        # No files found on disk, so no freshness data.
        assert result.stale_knowledge is False
        assert result.oldest_chunk_age_days is None
        assert result.freshness_caveat is None


class TestConsultationResultFreshnessFields:
    """ConsultationResult model has the new freshness fields with correct defaults."""

    def test_default_values(self) -> None:
        result = ConsultationResult(
            domain="security",
            expert_id="expert-security",
            expert_name="Security Expert",
            answer="Use parameterised queries.",
            confidence=0.85,
        )
        assert result.stale_knowledge is False
        assert result.oldest_chunk_age_days is None
        assert result.freshness_caveat is None

    def test_stale_values(self) -> None:
        result = ConsultationResult(
            domain="security",
            expert_id="expert-security",
            expert_name="Security Expert",
            answer="Old guidance.",
            confidence=0.6,
            stale_knowledge=True,
            oldest_chunk_age_days=450,
            freshness_caveat="Knowledge may be outdated.",
        )
        assert result.stale_knowledge is True
        assert result.oldest_chunk_age_days == 450
        assert result.freshness_caveat == "Knowledge may be outdated."

    def test_serialisation_round_trip(self) -> None:
        result = ConsultationResult(
            domain="testing-strategies",
            expert_id="expert-testing",
            expert_name="Testing Expert",
            answer="Test answer.",
            confidence=0.7,
            stale_knowledge=True,
            oldest_chunk_age_days=400,
            freshness_caveat="Note: outdated.",
        )
        data = result.model_dump()
        restored = ConsultationResult(**data)
        assert restored.stale_knowledge is True
        assert restored.oldest_chunk_age_days == 400
        assert restored.freshness_caveat == "Note: outdated."


class TestStaleKnowledgeNudge:
    """Nudge is generated for stale knowledge in tapps_consult_expert."""

    def test_nudge_triggered_when_stale(self) -> None:
        from tapps_mcp.common.nudges import compute_next_steps

        # Mock CallTracker to return empty called set.
        with patch(
            "tapps_mcp.common.nudges._get_call_tracker"
        ) as mock_tracker_fn:
            mock_tracker = mock_tracker_fn.return_value
            mock_tracker.get_called_tools.return_value = set()
            mock_tracker.total_calls.return_value = 0

            steps = compute_next_steps(
                "tapps_consult_expert",
                context={"stale_knowledge": True, "confidence": 0.8},
            )
            # The stale-knowledge nudge should be present.
            stale_nudges = [s for s in steps if "outdated" in s.lower()]
            assert len(stale_nudges) >= 1
            assert "tapps_lookup_docs()" in stale_nudges[0]

    def test_no_nudge_when_fresh(self) -> None:
        from tapps_mcp.common.nudges import compute_next_steps

        with patch(
            "tapps_mcp.common.nudges._get_call_tracker"
        ) as mock_tracker_fn:
            mock_tracker = mock_tracker_fn.return_value
            mock_tracker.get_called_tools.return_value = set()
            mock_tracker.total_calls.return_value = 0

            steps = compute_next_steps(
                "tapps_consult_expert",
                context={"stale_knowledge": False, "confidence": 0.8},
            )
            stale_nudges = [s for s in steps if "outdated" in s.lower()]
            assert len(stale_nudges) == 0


class TestFreshnessResultDataclass:
    """Tests for the _FreshnessResult dataclass."""

    def test_defaults(self) -> None:
        fr = _FreshnessResult()
        assert fr.stale_knowledge is False
        assert fr.oldest_chunk_age_days is None
        assert fr.freshness_caveat is None

    def test_with_values(self) -> None:
        fr = _FreshnessResult(
            stale_knowledge=True,
            oldest_chunk_age_days=500,
            freshness_caveat="Outdated.",
        )
        assert fr.stale_knowledge is True
        assert fr.oldest_chunk_age_days == 500
        assert fr.freshness_caveat == "Outdated."
