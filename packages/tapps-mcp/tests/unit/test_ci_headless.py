"""Tests for CI/Headless documentation text shipped inside CLAUDE.md.

The `generate_ci_workflow` generator was removed — TappsMCP no longer
writes a `tapps-quality.yml` into consumer projects. The CLAUDE.md docs
section that explains how to *invoke* tapps-mcp in CI if a consumer
chooses is still shipped.
"""

from __future__ import annotations

from tapps_mcp.pipeline.platform_generators import get_ci_claude_md_section


class TestClaudeMdCISection:
    def test_mentions_headless(self):
        section = get_ci_claude_md_section()
        assert "--headless" in section

    def test_mentions_enable_all_servers(self):
        section = get_ci_claude_md_section()
        assert "enableAllProjectMcpServers" in section

    def test_mentions_init_only(self):
        section = get_ci_claude_md_section()
        assert "--init-only" in section

    def test_mentions_validate_changed(self):
        section = get_ci_claude_md_section()
        assert "tapps_validate_changed" in section or "validate-changed" in section


class TestClaudeMdTemplate:
    def test_template_has_ci_section(self):
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        content = load_platform_rules("claude")
        assert "CI Integration" in content or "tapps_session_start" in content
