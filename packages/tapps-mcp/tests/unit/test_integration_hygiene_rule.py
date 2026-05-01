"""Tests for integration-hygiene rule generation (TAP-1215).

Verifies that ``generate_claude_integration_hygiene_rule`` writes the expected
file, that the rule content covers the three patterns documented in
``.claude/rules/integration-hygiene.md``, and that init / upgrade pipelines
invoke it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tapps_mcp.pipeline.platform_bundles import (
    _CLAUDE_INTEGRATION_HYGIENE_RULE,
    generate_claude_integration_hygiene_rule,
)


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return yaml.safe_load(parts[1]) or {}
    return {}


class TestRuleContent:
    """Inline content sanity checks — no file IO."""

    def test_always_apply(self) -> None:
        fm = _parse_frontmatter(_CLAUDE_INTEGRATION_HYGIENE_RULE)
        assert fm.get("alwaysApply") is True

    def test_covers_linear_oauth_pattern(self) -> None:
        assert "## Linear is OAuth via the Claude Code plugin" in _CLAUDE_INTEGRATION_HYGIENE_RULE
        assert "LINEAR_API_KEY" in _CLAUDE_INTEGRATION_HYGIENE_RULE

    def test_covers_no_client_state_mirror_pattern(self) -> None:
        assert (
            "## Don't mirror server-enforced state into the client"
            in _CLAUDE_INTEGRATION_HYGIENE_RULE
        )
        assert "Two sources of truth = guaranteed drift" in _CLAUDE_INTEGRATION_HYGIENE_RULE

    def test_covers_verify_subagent_claims_pattern(self) -> None:
        assert (
            "## Verify subagent claims about external APIs before citing them"
            in _CLAUDE_INTEGRATION_HYGIENE_RULE
        )
        assert "serialization site" in _CLAUDE_INTEGRATION_HYGIENE_RULE

    def test_documents_how_to_apply_checklist(self) -> None:
        assert "## How to apply" in _CLAUDE_INTEGRATION_HYGIENE_RULE
        # All three apply-checklist questions present.
        body = _CLAUDE_INTEGRATION_HYGIENE_RULE
        assert "Does the server already enforce this decision?" in body
        assert "Is the auth path I'm proposing already solved" in body
        assert "Does this claim about an external API come from a subagent" in body


class TestGenerateClaudeIntegrationHygieneRule:
    """File generation tests."""

    def test_creates_rule_file(self, tmp_path: Path) -> None:
        generate_claude_integration_hygiene_rule(tmp_path)
        assert (tmp_path / ".claude" / "rules" / "integration-hygiene.md").exists()

    def test_creates_rules_directory(self, tmp_path: Path) -> None:
        generate_claude_integration_hygiene_rule(tmp_path)
        assert (tmp_path / ".claude" / "rules").is_dir()

    def test_returns_created_action(self, tmp_path: Path) -> None:
        result = generate_claude_integration_hygiene_rule(tmp_path)
        assert result["action"] == "created"

    def test_returns_updated_on_overwrite(self, tmp_path: Path) -> None:
        generate_claude_integration_hygiene_rule(tmp_path)
        result = generate_claude_integration_hygiene_rule(tmp_path)
        assert result["action"] == "updated"

    def test_result_contains_file_path(self, tmp_path: Path) -> None:
        result = generate_claude_integration_hygiene_rule(tmp_path)
        assert "integration-hygiene.md" in result["file"]

    def test_written_content_matches_constant(self, tmp_path: Path) -> None:
        generate_claude_integration_hygiene_rule(tmp_path)
        written = (tmp_path / ".claude" / "rules" / "integration-hygiene.md").read_text(
            encoding="utf-8"
        )
        assert written == _CLAUDE_INTEGRATION_HYGIENE_RULE


class TestInitIntegration:
    """Verify tapps_init generates the integration-hygiene rule."""

    def test_init_generates_integration_hygiene_rule(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        result = bootstrap_pipeline(
            tmp_path,
            platform="claude",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "integration_hygiene_rule" in result
        assert result["integration_hygiene_rule"]["action"] == "created"
        assert (tmp_path / ".claude" / "rules" / "integration-hygiene.md").exists()


class TestUpgradeIntegration:
    """Verify tapps_upgrade regenerates the integration-hygiene rule."""

    def test_upgrade_regenerates_rule(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert "integration_hygiene_rule" in claude_result["components"]
        assert claude_result["components"]["integration_hygiene_rule"]["action"] == "created"

    def test_upgrade_respects_skip_token(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - .claude/rules/integration-hygiene.md\n",
            encoding="utf-8",
        )

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert "skipped" in str(claude_result["components"]["integration_hygiene_rule"])


class TestSecurityRulePurgesDeprecatedTools:
    """TAP-1214: shipped security rule must not reference removed tools."""

    def test_security_rule_drops_consult_expert_reference(self) -> None:
        from tapps_mcp.pipeline.platform_bundles import _CLAUDE_SECURITY_RULE

        assert "tapps_consult_expert" not in _CLAUDE_SECURITY_RULE

    def test_security_rule_drops_research_reference(self) -> None:
        from tapps_mcp.pipeline.platform_bundles import _CLAUDE_SECURITY_RULE

        assert "tapps_research" not in _CLAUDE_SECURITY_RULE

    def test_security_rule_points_at_lookup_docs(self) -> None:
        from tapps_mcp.pipeline.platform_bundles import _CLAUDE_SECURITY_RULE

        assert "tapps_lookup_docs" in _CLAUDE_SECURITY_RULE
