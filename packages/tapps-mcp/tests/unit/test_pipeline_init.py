"""Tests for the tapps_init bootstrap logic."""

from typing import ClassVar

from tapps_mcp import __version__
from tapps_mcp.pipeline.init import (
    _bootstrap_claude,
    _replace_tapps_section,
    bootstrap_pipeline,
)
from tapps_mcp.prompts.prompt_loader import load_agents_template, load_platform_rules


class TestBootstrapPipeline:
    def test_creates_handoff(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=True,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert "docs/TAPPS_HANDOFF.md" in result["created"]
        assert (tmp_path / "docs" / "TAPPS_HANDOFF.md").exists()
        content = (tmp_path / "docs" / "TAPPS_HANDOFF.md").read_text()
        assert "TAPPS Handoff" in content

    def test_creates_runlog(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=True,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert "docs/TAPPS_RUNLOG.md" in result["created"]
        assert (tmp_path / "docs" / "TAPPS_RUNLOG.md").exists()

    def test_creates_both(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert len(result["created"]) >= 2
        assert "docs/TAPPS_HANDOFF.md" in result["created"]
        assert "docs/TAPPS_RUNLOG.md" in result["created"]
        assert not result["errors"]

    def test_skips_existing_handoff(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "TAPPS_HANDOFF.md").write_text("existing content")
        result = bootstrap_pipeline(tmp_path)
        assert "docs/TAPPS_HANDOFF.md" in result["skipped"]
        # Should not overwrite
        assert (docs / "TAPPS_HANDOFF.md").read_text() == "existing content"

    def test_skips_existing_runlog(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "TAPPS_RUNLOG.md").write_text("existing log")
        result = bootstrap_pipeline(tmp_path, create_handoff=False)
        assert "docs/TAPPS_RUNLOG.md" in result["skipped"]

    def test_no_files_when_disabled(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert result["created"] == []
        assert result["skipped"] == []

    def test_claude_platform_creates_file(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="claude",
        )
        assert "CLAUDE.md" in result["created"]
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "TAPPS" in content

    def test_claude_platform_appends_to_existing(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# My Project\n\nExisting rules.\n")
        bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="claude",
        )
        content = (tmp_path / "CLAUDE.md").read_text()
        assert "My Project" in content  # Original preserved
        assert "TAPPS" in content  # Pipeline appended

    def test_claude_platform_skips_if_tapps_present(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Project\n\nUse TAPPS pipeline.\n")
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="claude",
        )
        # Should not appear in created since it was already there
        assert "CLAUDE.md" not in result["created"]

    def test_cursor_platform(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="cursor",
        )
        assert ".cursor/rules/tapps-pipeline.md" in result["created"]
        content = (tmp_path / ".cursor" / "rules" / "tapps-pipeline.md").read_text()
        assert "TAPPS" in content

    def test_unknown_platform_errors(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            platform="vscode",
        )
        assert len(result["errors"]) == 1
        assert "vscode" in result["errors"][0]

    def test_path_security(self, tmp_path):
        """Paths that escape project root should be rejected."""
        result = bootstrap_pipeline(
            tmp_path,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        for rel in result["created"]:
            full = (tmp_path / rel).resolve()
            assert str(full).startswith(str(tmp_path.resolve()))

    def test_creates_agents_md_when_missing(self, tmp_path):
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        assert "AGENTS.md" in result["created"]
        assert result["agents_md"]["action"] == "created"
        content = (tmp_path / "AGENTS.md").read_text()
        assert "TappsMCP" in content
        assert "tapps_server_info" in content

    def test_updates_agents_md_when_exists_and_outdated(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Custom agents\n")
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
        )
        # New behavior: outdated file is updated, not skipped
        assert result["agents_md"]["action"] == "updated"
        content = (tmp_path / "AGENTS.md").read_text()
        assert "tapps_server_info" in content  # template content merged in

    def test_creates_tech_stack_md(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\ndependencies = []\n")
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "TECH_STACK.md" in result["created"]
        assert result["tech_stack_md"]["action"] in ("created", "updated")
        content = (tmp_path / "TECH_STACK.md").read_text()
        assert "# Tech Stack" in content
        assert "Project Type" in content

    def test_server_verification_in_result(self, tmp_path):
        result = bootstrap_pipeline(tmp_path, create_handoff=False, create_runlog=False)
        assert "server_verification" in result
        sv = result["server_verification"]
        assert "ok" in sv
        assert "installed" in sv
        assert "missing_checkers" in sv

    def test_dry_run_skips_server_verification(self, tmp_path):
        """dry_run skips actual checker detection to stay lightweight."""
        result = bootstrap_pipeline(tmp_path, dry_run=True)
        sv = result["server_verification"]
        assert sv["skipped"] == "dry_run"
        assert sv["ok"] is True
        assert "message" in sv

    def test_verify_only_runs_only_server_verification(self, tmp_path):
        """verify_only returns immediately after server verification."""
        result = bootstrap_pipeline(tmp_path, verify_only=True)
        assert "server_verification" in result
        sv = result["server_verification"]
        assert "ok" in sv
        assert "installed" in sv
        assert "missing_checkers" in sv
        assert result["created"] == []
        assert "agents_md" not in result
        assert "tech_stack_md" not in result

    def test_cache_warming_in_result(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = []\n")
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=True,
            verify_server=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "cache_warming" in result
        cw = result["cache_warming"]
        assert "warmed" in cw
        assert "libraries" in cw

    def test_expert_rag_warming_in_result(self, tmp_path):
        """Expert RAG warming runs and returns expected structure."""
        (tmp_path / "pyproject.toml").write_text("[project]\ndependencies = []\n")
        result = bootstrap_pipeline(
            tmp_path,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=True,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=True,
        )
        assert "expert_rag_warming" in result
        erg = result["expert_rag_warming"]
        assert "warmed" in erg
        assert "attempted" in erg
        assert "domains" in erg
        assert isinstance(erg["domains"], list)


class TestAgentsMdIntegration:
    """Integration tests for AGENTS.md validate/update in bootstrap_pipeline."""

    _common: ClassVar[dict[str, bool]] = {
        "create_handoff": False,
        "create_runlog": False,
        "create_tech_stack_md": False,
        "verify_server": False,
        "warm_cache_from_tech_stack": False,
    }

    def test_validates_when_current(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text(load_agents_template(), encoding="utf-8")
        result = bootstrap_pipeline(tmp_path, **self._common)
        assert result["agents_md"]["action"] == "validated"
        assert "AGENTS.md" in result["skipped"]

    def test_updates_when_outdated(self, tmp_path):
        import re

        old = re.sub(
            r"<!--\s*tapps-agents-version:\s*[\d.]+\s*-->",
            "<!-- tapps-agents-version: 0.1.0 -->",
            load_agents_template(),
        )
        (tmp_path / "AGENTS.md").write_text(old, encoding="utf-8")
        result = bootstrap_pipeline(tmp_path, **self._common)
        assert result["agents_md"]["action"] == "updated"
        assert "changes" in result["agents_md"]
        assert len(result["agents_md"]["changes"]) > 0

    def test_overwrite_flag(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Custom only\n", encoding="utf-8")
        result = bootstrap_pipeline(tmp_path, **self._common, overwrite_agents_md=True)
        assert result["agents_md"]["action"] == "overwritten"
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "tapps_server_info" in content

    def test_still_creates_when_missing(self, tmp_path):
        result = bootstrap_pipeline(tmp_path, **self._common)
        assert result["agents_md"]["action"] == "created"
        assert "AGENTS.md" in result["created"]
        assert result["agents_md"]["version"] == __version__


class TestBootstrapClaudeOverwrite:
    """Tests for _bootstrap_claude() overwrite behaviour."""

    def test_claude_platform_overwrite_replaces_tapps_section(self, tmp_path):
        """When overwrite=True, the TAPPS section should be replaced, not duplicated."""
        claude_md = tmp_path / "CLAUDE.md"
        old_tapps = load_platform_rules("claude")
        user_content = "# My Project\n\nCustom content.\n"
        claude_md.write_text(user_content + "\n\n" + old_tapps, encoding="utf-8")

        action = _bootstrap_claude(tmp_path, overwrite=True)

        assert action == "updated"
        content = claude_md.read_text(encoding="utf-8")
        # Should have TAPPS content exactly once
        assert content.count("# TAPPS Quality Pipeline") == 1
        # Should preserve user content
        assert "# My Project" in content
        assert "Custom content." in content

    def test_claude_platform_overwrite_no_heading_falls_back(self, tmp_path):
        """When overwrite=True but no '# TAPPS Quality Pipeline' heading found,
        still replaces content via fallback."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "# My Project\n\nHas TAPPS reference but no heading.\n", encoding="utf-8"
        )

        action = _bootstrap_claude(tmp_path, overwrite=True)

        assert action == "updated"
        content = claude_md.read_text(encoding="utf-8")
        assert "# TAPPS Quality Pipeline" in content

    def test_claude_overwrite_false_skips_when_tapps_present(self, tmp_path):
        """When overwrite=False and TAPPS is already present, skip."""
        claude_md = tmp_path / "CLAUDE.md"
        old_tapps = load_platform_rules("claude")
        claude_md.write_text("# Project\n\n" + old_tapps, encoding="utf-8")

        action = _bootstrap_claude(tmp_path, overwrite=False)

        assert action == "skipped"

    def test_claude_creates_when_file_missing(self, tmp_path):
        """When CLAUDE.md does not exist, create it."""
        action = _bootstrap_claude(tmp_path)

        assert action == "created"
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "TAPPS" in content

    def test_claude_appends_when_no_tapps_present(self, tmp_path):
        """When CLAUDE.md exists but has no TAPPS content, append."""
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# My Project\n\nJust custom rules.\n", encoding="utf-8")

        action = _bootstrap_claude(tmp_path, overwrite=False)

        assert action == "updated"
        content = claude_md.read_text(encoding="utf-8")
        assert "# My Project" in content
        assert "TAPPS" in content


class TestReplaceTappsSection:
    """Tests for _replace_tapps_section() helper."""

    def test_replaces_tapps_section_preserving_surrounding(self):
        existing = (
            "# My Project\n\nIntro.\n\n"
            "# TAPPS Quality Pipeline\n\nOld content.\n\n"
            "# Another Section\n\nMore."
        )
        new_tapps = "# TAPPS Quality Pipeline - MANDATORY\n\nNew content."

        result = _replace_tapps_section(existing, new_tapps)

        assert "# My Project" in result
        assert "Intro." in result
        assert "New content." in result
        assert "Old content." not in result
        assert "# Another Section" in result
        assert "More." in result

    def test_replaces_tapps_at_end_of_file(self):
        existing = "# My Project\n\nIntro.\n\n# TAPPS Quality Pipeline\n\nOld content."
        new_tapps = "# TAPPS Quality Pipeline - MANDATORY\n\nNew content."

        result = _replace_tapps_section(existing, new_tapps)

        assert "# My Project" in result
        assert "New content." in result
        assert "Old content." not in result

    def test_fallback_when_no_tapps_heading(self):
        existing = "# My Project\n\nNo TAPPS heading here."
        new_tapps = "# TAPPS Quality Pipeline\n\nNew."

        result = _replace_tapps_section(existing, new_tapps)

        assert "# My Project" in result
        assert "# TAPPS Quality Pipeline" in result
        assert "New." in result

    def test_replaces_tapps_section_with_sub_headings(self):
        """TAPPS section with sub-headings (##, ###) should be fully replaced."""
        existing = (
            "# My Project\n\nIntro.\n\n"
            "# TAPPS Quality Pipeline\n\n## Sub heading\n\nOld sub content.\n\n"
            "# Another Section\n\nMore."
        )
        new_tapps = "# TAPPS Quality Pipeline\n\nFresh content only."

        result = _replace_tapps_section(existing, new_tapps)

        assert "Fresh content only." in result
        assert "Old sub content." not in result
        assert "# Another Section" in result
