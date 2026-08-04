"""Tests for thin Tier-1 budget and prose-duplication doctor checks (TAP-5549).

Kept as a sibling module (not appended to ``test_doctor.py``) so this file
scores cleanly on its own — see ``TestContextBudgetChecks`` in
``test_doctor.py`` for the pre-existing CLAUDE.md/AGENTS.md/skill checks.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.context_budget_thin_agent import (
    check_prose_duplication,
    check_tier1_thin_budget,
)


class TestTier1ThinBudget:
    """``check_tier1_thin_budget`` — opt-in 'Tier 1' section byte ceiling."""

    def test_no_tier1_marker_skips(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Hello\n\nNo tiers here.\n", encoding="utf-8")
        result = check_tier1_thin_budget(tmp_path)
        assert result.ok is True
        assert "skipping" in result.message.lower()

    def test_under_ceiling_passes(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text(
            "## Tier 1\n\nShort essentials.\n\n## Tier 2\n\nMore detail.\n",
            encoding="utf-8",
        )
        result = check_tier1_thin_budget(tmp_path)
        assert result.ok is True
        assert result.severity == "pass"

    def test_warns_over_warn_ceiling(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "doctor_context_budget:\n  tier1_warn_bytes: 50\n  tier1_fail_bytes: 5000\n",
            encoding="utf-8",
        )
        (tmp_path / "AGENTS.md").write_text(
            "## Tier 1\n\n" + ("essential guidance line\n" * 10) + "\n## Tier 2\n\nmore\n",
            encoding="utf-8",
        )
        result = check_tier1_thin_budget(tmp_path)
        assert result.ok is False
        assert result.severity == "warn"
        assert "WARN" in result.message

    def test_fails_over_fail_ceiling(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "doctor_context_budget:\n  tier1_warn_bytes: 50\n  tier1_fail_bytes: 100\n",
            encoding="utf-8",
        )
        (tmp_path / "AGENTS.md").write_text(
            "## Tier 1\n\n" + ("essential guidance line\n" * 20) + "\n## Tier 2\n\nmore\n",
            encoding="utf-8",
        )
        result = check_tier1_thin_budget(tmp_path)
        assert result.ok is False
        assert result.severity == "fail"
        assert not result.message.startswith("WARN")

    def test_section_stops_at_next_same_level_header(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "doctor_context_budget:\n  tier1_fail_bytes: 100000\n",
            encoding="utf-8",
        )
        (tmp_path / "AGENTS.md").write_text(
            "## Tier 1\n\nshort\n\n## Tier 2\n\n" + ("padding line\n" * 500),
            encoding="utf-8",
        )
        result = check_tier1_thin_budget(tmp_path)
        assert result.ok is True


class TestProseDuplication:
    """``check_prose_duplication`` — cross-file duplicated paragraph budget."""

    def test_only_one_file_present_skips(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Hello\n\nSome content.\n", encoding="utf-8")
        result = check_prose_duplication(tmp_path)
        assert result.ok is True
        assert "not both present" in result.message

    def test_no_duplicates_passes(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text(
            "# AGENTS\n\nThis paragraph is unique to the agents file and long enough.\n",
            encoding="utf-8",
        )
        (tmp_path / "CLAUDE.md").write_text(
            "# CLAUDE\n\nA completely different paragraph that shares nothing at all here.\n",
            encoding="utf-8",
        )
        result = check_prose_duplication(tmp_path)
        assert result.ok is True
        assert "No duplicated" in result.message

    def test_warns_over_warn_ceiling(self, tmp_path: Path) -> None:
        shared = "This exact paragraph is granted twice across both always-on files. " * 3
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "doctor_context_budget:\n"
            "  prose_duplication_warn_bytes: 50\n"
            "  prose_duplication_fail_bytes: 5000\n",
            encoding="utf-8",
        )
        (tmp_path / "AGENTS.md").write_text(f"# AGENTS\n\n{shared}\n", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text(f"# CLAUDE\n\n{shared}\n", encoding="utf-8")
        result = check_prose_duplication(tmp_path)
        assert result.ok is False
        assert result.severity == "warn"

    def test_fails_over_fail_ceiling(self, tmp_path: Path) -> None:
        shared = "This exact paragraph is granted twice across both always-on files. " * 3
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "doctor_context_budget:\n"
            "  prose_duplication_warn_bytes: 10\n"
            "  prose_duplication_fail_bytes: 50\n",
            encoding="utf-8",
        )
        (tmp_path / "AGENTS.md").write_text(f"# AGENTS\n\n{shared}\n", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text(f"# CLAUDE\n\n{shared}\n", encoding="utf-8")
        result = check_prose_duplication(tmp_path)
        assert result.ok is False
        assert result.severity == "fail"
        assert not result.message.startswith("WARN")

    def test_short_blocks_are_not_counted(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# H\n\nshort\n", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("# H\n\nshort\n", encoding="utf-8")
        result = check_prose_duplication(tmp_path)
        assert result.ok is True
