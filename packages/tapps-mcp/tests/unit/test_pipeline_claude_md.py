"""Tests for CLAUDE.md validation and smart-merge logic (TAP-2334)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp import __version__
from tapps_mcp.pipeline.claude_md import (
    EXPECTED_SECTIONS,
    ClaudeValidation,
    _ensure_stamp,
    merge_claude_md,
    render_fresh_claude_md,
    update_claude_md,
    validate_claude_md,
)
from tapps_mcp.pipeline.tapps_obligations_block import wrap_with_markers
from tapps_mcp.prompts.prompt_loader import load_platform_rules


def _obligations() -> str:
    return load_platform_rules("claude")


def _stamped_fresh() -> str:
    return render_fresh_claude_md(_obligations())


# ---------------------------------------------------------------------------
# ClaudeValidation
# ---------------------------------------------------------------------------


class TestClaudeValidation:
    def test_fresh_template_is_up_to_date(self) -> None:
        v = ClaudeValidation(_stamped_fresh())
        assert v.is_up_to_date
        assert v.existing_version == __version__
        assert v.has_obligations_block
        assert v.sections_missing == []
        assert set(v.sections_found) == set(EXPECTED_SECTIONS)

    def test_missing_version_marker(self) -> None:
        v = ClaudeValidation("# Project\n\n" + wrap_with_markers(_obligations()))
        assert v.existing_version is None
        assert v.needs_stamp
        assert v.needs_update

    def test_stale_stamp(self) -> None:
        stamped = f"<!-- tapps-claude-version: 0.0.1 -->\n{wrap_with_markers(_obligations())}\n"
        v = ClaudeValidation(stamped)
        assert v.existing_version == "0.0.1"
        assert v.needs_update
        assert not v.needs_stamp

    def test_missing_obligations_block(self) -> None:
        content = f"<!-- tapps-claude-version: {__version__} -->\n# Some custom CLAUDE.md\n"
        v = ClaudeValidation(content)
        assert not v.is_up_to_date
        assert not v.has_obligations_block
        assert v.sections_missing == EXPECTED_SECTIONS

    def test_user_content_preserved_in_validation(self) -> None:
        # User content outside markers does not affect validation outcomes.
        content = (
            f"<!-- tapps-claude-version: {__version__} -->\n"
            "# CLAUDE.md\n\n## My Notes\n\nProject-specific.\n\n"
            f"{wrap_with_markers(_obligations())}\n"
        )
        v = ClaudeValidation(content)
        assert v.is_up_to_date

    def test_to_dict_keys(self) -> None:
        v = ClaudeValidation(_stamped_fresh())
        d = v.to_dict()
        for key in (
            "existing_version",
            "current_version",
            "has_obligations_block",
            "sections_found",
            "sections_missing",
            "is_up_to_date",
            "needs_stamp",
        ):
            assert key in d
        assert d["current_version"] == __version__


# ---------------------------------------------------------------------------
# _ensure_stamp
# ---------------------------------------------------------------------------


class TestEnsureStamp:
    def test_adds_stamp_when_missing(self) -> None:
        new, action = _ensure_stamp("# CLAUDE.md\n\nbody.\n")
        assert action == "added"
        assert new.startswith(f"<!-- tapps-claude-version: {__version__} -->\n")
        assert "# CLAUDE.md" in new

    def test_unchanged_when_matching(self) -> None:
        original = f"<!-- tapps-claude-version: {__version__} -->\n# CLAUDE.md\n"
        new, action = _ensure_stamp(original)
        assert action == "unchanged"
        assert new == original

    def test_rewrites_stale_stamp(self) -> None:
        original = "<!-- tapps-claude-version: 0.0.1 -->\n# CLAUDE.md\n"
        new, action = _ensure_stamp(original)
        assert action == "updated"
        assert f"<!-- tapps-claude-version: {__version__} -->" in new
        assert "0.0.1" not in new

    def test_malformed_stamp_is_left_alone(self) -> None:
        # Garbage in the comment value: the regex matches digits/dots only,
        # so a non-matching malformed value is treated as absent and the
        # canonical stamp is prepended without erasing the malformed one.
        original = "<!-- tapps-claude-version: not-a-version -->\n# CLAUDE.md\n"
        new, action = _ensure_stamp(original)
        assert action == "added"
        assert new.startswith(f"<!-- tapps-claude-version: {__version__} -->\n")
        assert "not-a-version" in new


# ---------------------------------------------------------------------------
# merge_claude_md
# ---------------------------------------------------------------------------


class TestMergeClaudeMd:
    def test_merge_refreshes_stale_obligations_block(self) -> None:
        obligations = _obligations()
        # Existing file with an older obligations block but recent stamp.
        existing = (
            f"<!-- tapps-claude-version: {__version__} -->\n"
            "# CLAUDE.md\n\n"
            "<!-- BEGIN: tapps-obligations v0.0.1 -->\n"
            "Old obligation body.\n"
            "<!-- END: tapps-obligations -->\n"
        )
        merged, changes = merge_claude_md(existing, obligations)
        assert "refreshed_obligations_block" in changes
        assert f"<!-- BEGIN: tapps-obligations v{__version__} -->" in merged
        # User preamble survives.
        assert "# CLAUDE.md" in merged

    def test_merge_preserves_user_sections(self) -> None:
        obligations = _obligations()
        existing = (
            "<!-- tapps-claude-version: 0.0.1 -->\n"
            "# CLAUDE.md\n\n"
            "## My Custom Section\n\n"
            "Do not touch this.\n\n"
            f"{wrap_with_markers(obligations)}\n"
            "## Trailing User Notes\n\n"
            "Also preserve.\n"
        )
        merged, _changes = merge_claude_md(existing, obligations)
        assert "## My Custom Section" in merged
        assert "Do not touch this." in merged
        assert "## Trailing User Notes" in merged
        assert "Also preserve." in merged

    def test_merge_updates_stale_stamp(self) -> None:
        obligations = _obligations()
        existing = (
            "<!-- tapps-claude-version: 0.0.1 -->\n"
            f"{wrap_with_markers(obligations)}\n"
        )
        merged, changes = merge_claude_md(existing, obligations)
        assert f"<!-- tapps-claude-version: {__version__} -->" in merged
        assert "tapps-claude-version: 0.0.1" not in merged
        assert "updated_version_marker" in changes

    def test_merge_adds_missing_stamp(self) -> None:
        obligations = _obligations()
        existing = f"# CLAUDE.md\n\n{wrap_with_markers(obligations)}\n"
        merged, changes = merge_claude_md(existing, obligations)
        assert merged.startswith(f"<!-- tapps-claude-version: {__version__} -->\n")
        assert "added_version_marker" in changes

    def test_merge_migrates_legacy_unmarked_section(self) -> None:
        obligations = _obligations()
        legacy = (
            "# CLAUDE.md\n\n"
            "# TAPPS Quality Pipeline\n\n"
            "Some legacy body that the marker block should replace.\n\n"
            "# Other Heading\n\nuser content.\n"
        )
        merged, changes = merge_claude_md(legacy, obligations)
        assert "migrated_legacy_tapps_section" in changes
        assert "<!-- BEGIN: tapps-obligations" in merged
        assert "Some legacy body" not in merged
        assert "# Other Heading" in merged
        assert "user content." in merged

    def test_merge_appends_block_when_absent(self) -> None:
        obligations = _obligations()
        existing = "# CLAUDE.md\n\nProject readme.\n"
        merged, changes = merge_claude_md(existing, obligations)
        assert "appended_obligations_block" in changes
        assert "<!-- BEGIN: tapps-obligations" in merged
        assert "# CLAUDE.md" in merged
        assert "Project readme." in merged


# ---------------------------------------------------------------------------
# update_claude_md (filesystem integration)
# ---------------------------------------------------------------------------


class TestUpdateClaudeMd:
    def test_creates_when_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        obligations = _obligations()
        action, detail = update_claude_md(path, obligations)
        assert action == "created"
        assert detail["changes"] == ["created"]
        assert path.read_text(encoding="utf-8").startswith(
            f"<!-- tapps-claude-version: {__version__} -->\n"
        )

    def test_up_to_date_returns_validated(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        path.write_text(_stamped_fresh(), encoding="utf-8")
        action, detail = update_claude_md(path, _obligations())
        assert action == "validated"
        assert detail["changes"] == []
        assert detail["validation"]["is_up_to_date"]

    def test_outdated_returns_updated(self, tmp_path: Path) -> None:
        obligations = _obligations()
        path = tmp_path / "CLAUDE.md"
        path.write_text(
            "<!-- tapps-claude-version: 0.0.1 -->\n"
            f"{wrap_with_markers(obligations)}\n",
            encoding="utf-8",
        )
        action, detail = update_claude_md(path, obligations)
        assert action == "updated"
        assert len(detail["changes"]) > 0
        content = path.read_text(encoding="utf-8")
        assert __version__ in content

    def test_overwrite_forces_merge_preserving_user_content(self, tmp_path: Path) -> None:
        """``overwrite=True`` forces the merge even on up-to-date files, but
        surrounding user content (outside the marker block) is preserved."""
        path = tmp_path / "CLAUDE.md"
        path.write_text(_stamped_fresh() + "\n## User Section\n\nKeep me.\n", encoding="utf-8")
        action, detail = update_claude_md(path, _obligations(), overwrite=True)
        assert action == "overwritten"
        assert "changes" in detail
        content = path.read_text(encoding="utf-8")
        assert "## User Section" in content
        assert "Keep me." in content
        assert "<!-- BEGIN: tapps-obligations" in content

    def test_legacy_no_stamp_returns_needs_stamp(self, tmp_path: Path) -> None:
        """Files without a stamp get treated as legacy: add stamp + refresh
        obligations block, but do not touch user content."""
        obligations = _obligations()
        path = tmp_path / "CLAUDE.md"
        path.write_text(
            "# CLAUDE.md\n\n## My Project\n\nProject body.\n\n"
            f"{wrap_with_markers(obligations)}\n",
            encoding="utf-8",
        )
        action, detail = update_claude_md(path, obligations)
        assert action == "needs-stamp"
        content = path.read_text(encoding="utf-8")
        assert content.startswith(f"<!-- tapps-claude-version: {__version__} -->\n")
        assert "## My Project" in content
        assert "Project body." in content

    def test_user_customizations_survive_merge(self, tmp_path: Path) -> None:
        obligations = _obligations()
        path = tmp_path / "CLAUDE.md"
        path.write_text(
            "<!-- tapps-claude-version: 0.0.1 -->\n"
            "# CLAUDE.md\n\n## Project notes\n\nKeep me.\n\n"
            f"{wrap_with_markers(obligations)}\n"
            "## Trailing user content\n\nAlso keep.\n",
            encoding="utf-8",
        )
        action, _detail = update_claude_md(path, obligations)
        assert action == "updated"
        content = path.read_text(encoding="utf-8")
        assert "## Project notes" in content
        assert "Keep me." in content
        assert "## Trailing user content" in content
        assert "Also keep." in content
        assert f"<!-- tapps-claude-version: {__version__} -->" in content

    def test_idempotent_across_repeated_updates(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        obligations = _obligations()
        update_claude_md(path, obligations)
        first = path.read_text(encoding="utf-8")
        update_claude_md(path, obligations)
        second = path.read_text(encoding="utf-8")
        assert first == second


# ---------------------------------------------------------------------------
# validate_claude_md (filesystem)
# ---------------------------------------------------------------------------


class TestValidateClaudeMd:
    def test_validate_reads_file(self, tmp_path: Path) -> None:
        path = tmp_path / "CLAUDE.md"
        path.write_text(_stamped_fresh(), encoding="utf-8")
        v = validate_claude_md(path)
        assert v.is_up_to_date
        assert v.existing_version == __version__
