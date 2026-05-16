"""Tests for AGENTS.md validation and smart-merge logic."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp import __version__
from tapps_mcp.pipeline.agents_md import (
    EXPECTED_SECTIONS,
    EXPECTED_TOOLS,
    AgentsValidation,
    _split_into_sections,
    merge_agents_md,
    update_agents_md,
    validate_agents_md,
)
from tapps_mcp.prompts.prompt_loader import load_agents_template

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _template() -> str:
    return load_agents_template()


def _template_with_version(version: str) -> str:
    """Return template content with a specific version marker."""
    content = _template()
    import re

    return re.sub(
        r"<!--\s*tapps-agents-version:\s*[\d.]+\s*-->",
        f"<!-- tapps-agents-version: {version} -->",
        content,
    )


def _template_without_section(section: str) -> str:
    """Return template with one ## section removed."""
    content = _template()
    lines = content.splitlines(keepends=True)
    result: list[str] = []
    skip = False
    for line in lines:
        if line.strip() == f"## {section}":
            skip = True
            continue
        if skip and line.startswith("## "):
            skip = False
        if skip:
            continue
        result.append(line)
    return "".join(result)


# ---------------------------------------------------------------------------
# AgentsValidation
# ---------------------------------------------------------------------------


class TestAgentsValidation:
    def test_fresh_template_is_up_to_date(self) -> None:
        v = AgentsValidation(_template())
        assert v.is_up_to_date
        assert v.existing_version == __version__
        assert v.sections_missing == []
        assert v.tools_missing == []
        assert len(v.sections_found) == len(EXPECTED_SECTIONS)
        assert len(v.tools_found) == len(EXPECTED_TOOLS)

    def test_missing_version_marker(self) -> None:
        content = "# TappsMCP\n\nSome content mentioning all tools.\n"
        v = AgentsValidation(content)
        assert v.existing_version is None
        assert v.needs_update

    def test_old_version(self) -> None:
        content = _template_with_version("0.1.0")
        v = AgentsValidation(content)
        assert v.existing_version == "0.1.0"
        assert v.needs_update

    def test_missing_section_detected(self) -> None:
        content = _template_without_section("Recommended workflow")
        v = AgentsValidation(content)
        assert "Recommended workflow" in v.sections_missing
        assert "Recommended workflow" not in v.sections_found

    def test_missing_tool_detected(self) -> None:
        content = _template().replace("tapps_session_start", "tapps_session")
        v = AgentsValidation(content)
        assert "tapps_session_start" in v.tools_missing

    def test_user_custom_sections_ignored(self) -> None:
        content = _template() + "\n## My Custom Section\n\nCustom content.\n"
        v = AgentsValidation(content)
        assert v.is_up_to_date  # Custom sections don't affect validation

    def test_to_dict_keys(self) -> None:
        v = AgentsValidation(_template())
        d = v.to_dict()
        assert "existing_version" in d
        assert "current_version" in d
        assert "sections_found" in d
        assert "sections_missing" in d
        assert "tools_found" in d
        assert "tools_missing" in d
        assert "is_up_to_date" in d
        assert d["current_version"] == __version__


# ---------------------------------------------------------------------------
# _split_into_sections
# ---------------------------------------------------------------------------


class TestSplitIntoSections:
    def test_split_simple(self) -> None:
        content = "## First\nBody 1\n## Second\nBody 2\n"
        parts = _split_into_sections(content)
        assert len(parts) == 2
        assert parts[0][0] == "First"
        assert "Body 1" in parts[0][1]
        assert parts[1][0] == "Second"
        assert "Body 2" in parts[1][1]

    def test_split_with_preamble(self) -> None:
        content = "# Title\n\nIntro text.\n\n## First\nBody.\n"
        parts = _split_into_sections(content)
        assert len(parts) == 2
        assert parts[0][0] is None  # Preamble
        assert "Title" in parts[0][1]
        assert parts[1][0] == "First"

    def test_split_empty(self) -> None:
        parts = _split_into_sections("")
        assert parts == []


# ---------------------------------------------------------------------------
# merge_agents_md
# ---------------------------------------------------------------------------


class TestMergeAgentsMd:
    def test_merge_identical(self) -> None:
        template = _template()
        merged, changes = merge_agents_md(template, template)
        assert changes == []
        assert merged.strip() == template.strip()

    def test_merge_adds_missing_section(self) -> None:
        existing = _template_without_section("Checklist task types")
        template = _template()
        merged, changes = merge_agents_md(existing, template)
        assert any("added_section:Checklist task types" in c for c in changes)
        assert "## Checklist task types" in merged

    def test_merge_updates_stale_section(self) -> None:
        template = _template()
        # Modify a section body in the existing file (Essential tools table)
        existing = template.replace(
            "**tapps_session_start** | **FIRST call in every session**",
            "**tapps_session_start** | OLD description",
        )
        merged, changes = merge_agents_md(existing, template)
        assert any("updated_section:Essential tools (always-on workflow)" in c for c in changes)
        # Merged should have the template version
        assert "FIRST call in every session" in merged

    def test_merge_preserves_user_sections(self) -> None:
        template = _template()
        existing = template + "\n## My Custom Rules\n\nDo not touch this.\n"
        merged, changes = merge_agents_md(existing, template)
        assert "## My Custom Rules" in merged
        assert "Do not touch this." in merged

    def test_merge_adds_version_marker(self) -> None:
        # Existing content without version marker — version comes via
        # the template preamble replacement, not the fallback path.
        existing = "# TappsMCP\n\n## Essential tools (always-on workflow)\n\nSome content.\n"
        template = _template()
        merged, changes = merge_agents_md(existing, template)
        assert "tapps-agents-version" in merged
        assert "updated_preamble" in changes

    def test_merge_updates_preamble(self) -> None:
        template = _template()
        # Modify preamble
        existing = template.replace(
            "code quality, doc lookup, and domain expert advice",
            "old quality advice",
        )
        merged, changes = merge_agents_md(existing, template)
        assert "updated_preamble" in changes
        assert "code quality, doc lookup, and domain expert advice" in merged


# ---------------------------------------------------------------------------
# update_agents_md (filesystem integration)
# ---------------------------------------------------------------------------


class TestUpdateAgentsMd:
    def test_up_to_date_returns_validated(self, tmp_path: Path) -> None:
        agents = tmp_path / "AGENTS.md"
        template = _template()
        agents.write_text(template, encoding="utf-8")

        action, detail = update_agents_md(agents, template)
        assert action == "validated"
        assert detail["changes"] == []
        assert detail["validation"]["is_up_to_date"]

    def test_outdated_returns_updated(self, tmp_path: Path) -> None:
        agents = tmp_path / "AGENTS.md"
        template = _template()
        old = _template_with_version("0.1.0")
        agents.write_text(old, encoding="utf-8")

        action, detail = update_agents_md(agents, template)
        assert action == "updated"
        assert len(detail["changes"]) > 0
        # File should now contain the current version
        content = agents.read_text(encoding="utf-8")
        assert __version__ in content

    def test_overwrite_replaces_entirely(self, tmp_path: Path) -> None:
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Custom content only\n", encoding="utf-8")
        template = _template()

        action, detail = update_agents_md(agents, template, overwrite=True)
        assert action == "overwritten"
        assert detail["changes"] == ["full_overwrite"]
        assert agents.read_text(encoding="utf-8") == template

    def test_preserves_user_content(self, tmp_path: Path) -> None:
        agents = tmp_path / "AGENTS.md"
        template = _template()
        custom = template + "\n## My Project Notes\n\nKeep this.\n"
        agents.write_text(custom, encoding="utf-8")

        action, detail = update_agents_md(agents, template)
        assert action == "validated"
        content = agents.read_text(encoding="utf-8")
        assert "## My Project Notes" in content
        assert "Keep this." in content


# ---------------------------------------------------------------------------
# validate_agents_md (filesystem)
# ---------------------------------------------------------------------------


class TestValidateAgentsMd:
    def test_validate_reads_file(self, tmp_path: Path) -> None:
        agents = tmp_path / "AGENTS.md"
        agents.write_text(_template(), encoding="utf-8")
        v = validate_agents_md(agents)
        assert v.is_up_to_date
        assert v.existing_version == __version__


# ---------------------------------------------------------------------------
# Karpathy-block excision (regression: duplicate section on upgrade)
# ---------------------------------------------------------------------------


class TestMergePreservesKarpathyBlock:
    """Regression tests for the upgrade-time Karpathy duplication bug.

    Before 2.10.1, merge_agents_md treated the block's inner `## Karpathy
    Behavioral Guidelines` heading as a user section.  The BEGIN marker
    lived inside the preceding EXPECTED section's body, so replacing that
    section's body with the template version silently dropped the BEGIN
    marker, leaving install_or_refresh to find no block and append a
    duplicate.
    """

    @staticmethod
    def _block() -> str:
        from tapps_mcp.prompts.prompt_loader import load_karpathy_guidelines

        return load_karpathy_guidelines()

    def test_existing_karpathy_block_is_excised_from_merge_output(self) -> None:
        """merge_agents_md must strip the block so install_or_refresh can re-add it."""
        template = _template()
        existing = _template_with_version("2.9.0") + "\n\n" + self._block() + "\n"

        merged, changes = merge_agents_md(existing, template)

        # Block is excised — install_or_refresh runs after merge to re-install.
        assert "<!-- BEGIN: karpathy-guidelines" not in merged
        assert "<!-- END: karpathy-guidelines -->" not in merged
        assert "## Karpathy Behavioral Guidelines" not in merged
        assert "excised_karpathy_block" in changes

    def test_legacy_unwrapped_karpathy_section_is_removed(self) -> None:
        """Pre-marker installs left a bare ## Karpathy section; merge must clean it."""
        template = _template()
        legacy = (
            "## Karpathy Behavioral Guidelines\n\n"
            "> Source: https://github.com/forrestchang/andrej-karpathy-skills\n\n"
            "Some vendored body text.\n\n"
            "<!-- END: karpathy-guidelines -->\n"
        )
        # Place the legacy section between two EXPECTED sections to mirror
        # the real-world layout that triggered the bug in tapps-mcp itself.
        existing = _template_with_version("2.9.0").replace(
            "## Using tapps_lookup_docs for domain guidance",
            legacy + "## Using tapps_lookup_docs for domain guidance",
            1,
        )

        merged, changes = merge_agents_md(existing, template)

        assert "## Karpathy Behavioral Guidelines" not in merged
        assert "<!-- END: karpathy-guidelines -->" not in merged
        assert "excised_karpathy_block" in changes

    def test_idempotent_across_repeated_merges(self) -> None:
        """Running the full merge + re-install cycle twice yields identical output."""
        from tapps_mcp.pipeline.karpathy_block import install_or_refresh

        # Simulate the upgrade pipeline: merge_agents_md runs first, then
        # install_or_refresh appends the block.  Two cycles must produce
        # the same file (no accumulating duplicates).
        template = _template()
        starting = _template_with_version("2.9.0") + "\n\n" + self._block() + "\n"

        def cycle(content: str, path: Path) -> str:
            merged, _ = merge_agents_md(content, template)
            path.write_text(merged, encoding="utf-8")
            install_or_refresh(path)
            return path.read_text(encoding="utf-8")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "AGENTS.md"
            after_one = cycle(starting, p)
            after_two = cycle(after_one, p)

        assert after_one == after_two
        assert after_one.count("<!-- BEGIN: karpathy-guidelines") == 1
        assert after_one.count("<!-- END: karpathy-guidelines -->") == 1
        assert after_one.count("## Karpathy Behavioral Guidelines") == 1


# ---------------------------------------------------------------------------
# TAP-1795: merge_agents_md must rewrite a stale version stamp, not leave it.
# ---------------------------------------------------------------------------


class TestMergeUpdatesStaleVersionMarker:
    """The merge rewrites canonical sections from the template; the version
    stamp must follow or `is_up_to_date` lies and skip-merge heuristics lock
    consumers on stale content."""

    def test_stale_stamp_is_rewritten_to_current(self) -> None:
        template = _template()
        existing = _template_with_version("0.0.1")
        merged, changes = merge_agents_md(existing, template)
        assert f"<!-- tapps-agents-version: {__version__} -->" in merged
        assert f"tapps-agents-version: 0.0.1" not in merged
        assert "updated_version_marker" in changes

    def test_current_stamp_is_left_alone(self) -> None:
        template = _template()
        merged, changes = merge_agents_md(template, template)
        assert f"<!-- tapps-agents-version: {__version__} -->" in merged
        assert "updated_version_marker" not in changes
        assert "added_version_marker" not in changes

    def test_no_stamp_falls_back_to_prepend(self) -> None:
        # No stamp anywhere in the existing content. The prepend path must still
        # fire (not the rewrite path) and record `added_version_marker`.
        existing = "# TappsMCP\n\n## Essential tools (always-on workflow)\n\nSome content.\n"
        template = _template()
        merged, changes = merge_agents_md(existing, template)
        assert f"<!-- tapps-agents-version: {__version__} -->" in merged
        # When the preamble path runs, it writes the stamp itself, so the
        # fallback `added_version_marker` may not be needed. Either way we must
        # NOT see `updated_version_marker` because there was no stamp to update.
        assert "updated_version_marker" not in changes
