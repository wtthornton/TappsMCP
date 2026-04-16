"""Tests for docs_mcp.generators.adr -- Architecture Decision Record generation.

Covers ADRRecord model defaults, ADRGenerator numbering, MADR and Nygard format
rendering, filename slugification, supersedes links, index generation,
validation fallbacks, and the ``docs_generate_adr`` MCP tool handler.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from docs_mcp.generators.adr import ADRGenerator, ADRRecord
from tests.helpers import make_settings as _make_settings

# ---------------------------------------------------------------------------
# ADRRecord model
# ---------------------------------------------------------------------------


class TestADRRecord:
    """Tests for the ADRRecord Pydantic model defaults and fields."""

    def test_default_status_is_proposed(self) -> None:
        """New records default to 'proposed' status."""
        record = ADRRecord(number=1, title="Test Decision")
        assert record.status == "proposed"

    def test_default_date_is_empty(self) -> None:
        """Date defaults to empty string (auto-filled by generator)."""
        record = ADRRecord(number=1, title="Test Decision")
        assert record.date == ""

    def test_default_supersedes_is_none(self) -> None:
        """Supersedes defaults to None."""
        record = ADRRecord(number=1, title="Test Decision")
        assert record.supersedes is None

    def test_valid_statuses_accepted(self) -> None:
        """All four valid statuses can be set on the model."""
        for status in ("proposed", "accepted", "deprecated", "superseded"):
            record = ADRRecord(number=1, title="Decision", status=status)
            assert record.status == status

    def test_fields_populate(self) -> None:
        """All fields populate correctly."""
        record = ADRRecord(
            number=5,
            title="Use Postgres",
            status="accepted",
            date="2026-03-01",
            context="We need a database.",
            decision="Use Postgres.",
            consequences="Need DBA skills.",
            supersedes=2,
        )
        assert record.number == 5
        assert record.title == "Use Postgres"
        assert record.context == "We need a database."
        assert record.supersedes == 2


# ---------------------------------------------------------------------------
# Auto-numbering
# ---------------------------------------------------------------------------


class TestADRGeneratorNumbering:
    """Tests for auto-numbering from existing ADR files."""

    def test_empty_dir_starts_at_one(self, tmp_path: Path) -> None:
        """When the ADR directory is empty, numbering starts at 1."""
        gen = ADRGenerator()
        content, filename = gen.generate(
            "First Decision",
            project_root=tmp_path,
            adr_dir=tmp_path,
        )
        assert filename == "0001-first-decision.md"
        assert "# 1. First Decision" in content

    def test_nonexistent_dir_starts_at_one(self, tmp_path: Path) -> None:
        """When the ADR directory does not exist, numbering starts at 1."""
        gen = ADRGenerator()
        missing = tmp_path / "no_such_dir"
        content, filename = gen.generate(
            "New Decision",
            project_root=tmp_path,
            adr_dir=missing,
        )
        assert filename == "0001-new-decision.md"

    def test_continues_from_existing_adrs(self, tmp_path: Path) -> None:
        """Numbering continues after the highest existing ADR number."""
        adr_dir = tmp_path / "decisions"
        adr_dir.mkdir()
        (adr_dir / "0001-first-decision.md").write_text(
            "# 1. First Decision\n\n## Status\n\naccepted\n",
            encoding="utf-8",
        )
        (adr_dir / "0002-second-decision.md").write_text(
            "# 2. Second Decision\n\n## Status\n\nproposed\n",
            encoding="utf-8",
        )

        gen = ADRGenerator()
        content, filename = gen.generate(
            "Third Decision",
            project_root=tmp_path,
            adr_dir=adr_dir,
        )
        assert filename == "0003-third-decision.md"
        assert "# 3. Third Decision" in content


# ---------------------------------------------------------------------------
# MADR format
# ---------------------------------------------------------------------------


class TestADRGeneratorMADR:
    """Tests for MADR (Markdown Any Decision Records) template output."""

    def test_madr_has_required_sections(self, tmp_path: Path) -> None:
        """MADR output contains Status, Context, Decision, Consequences."""
        gen = ADRGenerator()
        content, _ = gen.generate(
            "Use FastMCP",
            template="madr",
            context="Need an MCP framework.",
            decision="Use FastMCP.",
            consequences="Faster development.",
            project_root=tmp_path,
        )
        assert "## Status" in content
        assert "## Context" in content
        assert "## Decision" in content
        assert "## Consequences" in content

    def test_madr_includes_date(self, tmp_path: Path) -> None:
        """MADR output includes a Date: line."""
        gen = ADRGenerator()
        content, _ = gen.generate("Date Check", project_root=tmp_path)
        assert "Date:" in content

    def test_madr_renders_user_content(self, tmp_path: Path) -> None:
        """User-provided context, decision, consequences appear in output."""
        gen = ADRGenerator()
        content, _ = gen.generate(
            "Custom Content",
            template="madr",
            context="My custom context.",
            decision="My custom decision.",
            consequences="My custom consequences.",
            project_root=tmp_path,
        )
        assert "My custom context." in content
        assert "My custom decision." in content
        assert "My custom consequences." in content

    def test_madr_placeholder_when_empty(self, tmp_path: Path) -> None:
        """Empty fields get placeholder text in MADR format."""
        gen = ADRGenerator()
        content, _ = gen.generate("Placeholders", template="madr", project_root=tmp_path)
        assert "Describe the context" in content
        assert "Describe the decision" in content
        assert "Describe the consequences" in content


# ---------------------------------------------------------------------------
# Nygard format
# ---------------------------------------------------------------------------


class TestADRGeneratorNygard:
    """Tests for Nygard (Michael Nygard) template output."""

    def test_nygard_has_required_sections(self, tmp_path: Path) -> None:
        """Nygard output contains Status, Context, Decision, Consequences."""
        gen = ADRGenerator()
        content, _ = gen.generate("Nygard Test", template="nygard", project_root=tmp_path)
        assert "## Status" in content
        assert "## Context" in content
        assert "## Decision" in content
        assert "## Consequences" in content

    def test_nygard_placeholder_text(self, tmp_path: Path) -> None:
        """Nygard format uses its own placeholder wording."""
        gen = ADRGenerator()
        content, _ = gen.generate("Nygard Placeholders", template="nygard", project_root=tmp_path)
        assert "What is the issue" in content
        assert "What is the change" in content
        assert "What becomes easier or more difficult" in content


# ---------------------------------------------------------------------------
# Filename slugification
# ---------------------------------------------------------------------------


class TestADRGeneratorFilename:
    """Tests for slug-based filename generation."""

    def test_simple_title_slugified(self, tmp_path: Path) -> None:
        """Simple title becomes a lowercase-hyphenated slug."""
        gen = ADRGenerator()
        _, filename = gen.generate("Use PostgreSQL", project_root=tmp_path)
        assert filename == "0001-use-postgresql.md"

    def test_special_characters_removed(self, tmp_path: Path) -> None:
        """Special characters are stripped from slugs."""
        gen = ADRGenerator()
        _, filename = gen.generate("Use C++ (v2.0)!", project_root=tmp_path)
        # Parentheses, exclamation mark, plus signs removed
        assert "(" not in filename
        assert "!" not in filename
        assert filename.startswith("0001-")
        assert filename.endswith(".md")

    def test_multiple_spaces_collapsed(self, tmp_path: Path) -> None:
        """Multiple spaces become a single hyphen."""
        gen = ADRGenerator()
        _, filename = gen.generate("Use   Multiple   Spaces", project_root=tmp_path)
        assert "--" not in filename.replace("0001-", "")


# ---------------------------------------------------------------------------
# Supersedes link
# ---------------------------------------------------------------------------


class TestADRGeneratorSupersedes:
    """Tests for the supersedes link in MADR output."""

    def test_supersedes_appears_in_madr(self, tmp_path: Path) -> None:
        """When supersedes is set, MADR output includes a reference."""
        gen = ADRGenerator()
        record = ADRRecord(
            number=3,
            title="Replace DB",
            status="accepted",
            date="2026-03-01",
            supersedes=1,
        )
        content = gen._render_madr(record)
        assert "Supersedes [ADR 1]" in content
        assert "0001-*.md" in content

    def test_no_supersedes_when_none(self, tmp_path: Path) -> None:
        """When supersedes is None, no supersedes link appears."""
        gen = ADRGenerator()
        record = ADRRecord(
            number=2,
            title="Keep DB",
            status="accepted",
            date="2026-03-01",
        )
        content = gen._render_madr(record)
        assert "Supersedes" not in content


# ---------------------------------------------------------------------------
# Index generation
# ---------------------------------------------------------------------------


class TestADRGeneratorIndex:
    """Tests for the ADR index table generation."""

    def test_index_from_existing_adrs(self, tmp_path: Path) -> None:
        """Index table lists all ADR files with number, title, status, date."""
        adr_dir = tmp_path / "decisions"
        adr_dir.mkdir()
        (adr_dir / "0001-first-decision.md").write_text(
            "# 1. First Decision\n\nDate: 2026-01-10\n\n## Status\n\naccepted\n",
            encoding="utf-8",
        )
        (adr_dir / "0002-second-decision.md").write_text(
            "# 2. Second Decision\n\nDate: 2026-02-15\n\n## Status\n\nproposed\n",
            encoding="utf-8",
        )

        gen = ADRGenerator()
        index = gen.generate_index(adr_dir)

        assert "# Architecture Decision Records" in index
        assert "| Number | Title | Status | Date |" in index
        assert "| 1 | First Decision | accepted | 2026-01-10 |" in index
        assert "| 2 | Second Decision | proposed | 2026-02-15 |" in index

    def test_index_empty_dir(self, tmp_path: Path) -> None:
        """Index from an empty directory returns header-only table."""
        adr_dir = tmp_path / "empty_decisions"
        adr_dir.mkdir()

        gen = ADRGenerator()
        index = gen.generate_index(adr_dir)

        assert "# Architecture Decision Records" in index
        assert "| Number | Title | Status | Date |" in index
        # No data rows
        lines = [
            l
            for l in index.strip().splitlines()
            if l.startswith("| ") and "Number" not in l and "---" not in l
        ]
        assert len(lines) == 0

    def test_index_nonexistent_dir(self, tmp_path: Path) -> None:
        """Index from a nonexistent directory returns header-only table."""
        gen = ADRGenerator()
        index = gen.generate_index(tmp_path / "does_not_exist")
        assert "# Architecture Decision Records" in index


# ---------------------------------------------------------------------------
# Validation fallbacks
# ---------------------------------------------------------------------------


class TestADRGeneratorValidation:
    """Tests for invalid input fallback behavior."""

    def test_invalid_template_falls_back_to_madr(self, tmp_path: Path) -> None:
        """Unknown template name falls back to 'madr'."""
        gen = ADRGenerator()
        content, _ = gen.generate(
            "Fallback Template",
            template="unknown_format",
            project_root=tmp_path,
        )
        # MADR placeholders should be present (not Nygard)
        assert "Describe the context" in content

    def test_invalid_status_falls_back_to_proposed(self, tmp_path: Path) -> None:
        """Unknown status falls back to 'proposed'."""
        gen = ADRGenerator()
        content, _ = gen.generate(
            "Fallback Status",
            status="invalid_status",
            project_root=tmp_path,
        )
        assert "\nproposed\n" in content


# ---------------------------------------------------------------------------
# MCP tool handler
# ---------------------------------------------------------------------------


class TestADRMCPTool:
    """Tests for the ``docs_generate_adr`` MCP tool handler."""

    async def test_generate_adr_response_envelope(self, tmp_path: Path) -> None:
        """Response has the standard success_response envelope."""
        root = tmp_path / "proj"
        root.mkdir()

        from docs_mcp.server_gen_tools import docs_generate_adr

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_adr(
                title="Use MCP Protocol",
                project_root=str(root),
            )

        assert result["tool"] == "docs_generate_adr"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert "data" in result
        data = result["data"]
        assert data["template"] == "madr"
        assert data["filename"].startswith("0001-")
        assert "written_to" in data

    async def test_generate_adr_nygard_template(self, tmp_path: Path) -> None:
        """Nygard template via MCP tool produces nygard-style content."""
        root = tmp_path / "proj"
        root.mkdir()

        from docs_mcp.server_gen_tools import docs_generate_adr

        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(root),
        ):
            result = await docs_generate_adr(
                title="Choose Database",
                template="nygard",
                project_root=str(root),
            )

        assert result["success"] is True
        assert result["data"]["template"] == "nygard"
        written = (root / result["data"]["written_to"]).read_text()
        assert "What is the issue" in written

    async def test_generate_adr_invalid_root(self, tmp_path: Path) -> None:
        """Non-existent project root returns an error."""
        from docs_mcp.server_gen_tools import docs_generate_adr

        fake = tmp_path / "no_such_dir"
        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=_make_settings(fake),
        ):
            result = await docs_generate_adr(
                title="Orphan ADR",
                project_root=str(fake),
            )

        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"
