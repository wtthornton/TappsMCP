"""Tests for linear-standards rule generation (TAP-980 Phase A).

Verifies that ``generate_claude_linear_standards_rule`` writes the expected
file, that the rule content documents the docs-mcp routing flow and the
Linear markdown workarounds, and that init / upgrade pipelines invoke it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tapps_mcp.pipeline.platform_bundles import (
    _CLAUDE_LINEAR_STANDARDS_RULE,
    generate_claude_linear_standards_rule,
)


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return yaml.safe_load(parts[1]) or {}
    return {}


class TestRuleContent:
    """Inline content sanity checks — no file IO."""

    def test_always_apply(self) -> None:
        fm = _parse_frontmatter(_CLAUDE_LINEAR_STANDARDS_RULE)
        assert fm.get("alwaysApply") is True

    def test_mentions_docs_generate_epic(self) -> None:
        assert "docs_generate_epic" in _CLAUDE_LINEAR_STANDARDS_RULE

    def test_mentions_docs_generate_story(self) -> None:
        assert "docs_generate_story" in _CLAUDE_LINEAR_STANDARDS_RULE

    def test_mentions_docs_validate_linear_issue(self) -> None:
        assert "docs_validate_linear_issue" in _CLAUDE_LINEAR_STANDARDS_RULE

    def test_mentions_snapshot_invalidate(self) -> None:
        assert "tapps_linear_snapshot_invalidate" in _CLAUDE_LINEAR_STANDARDS_RULE

    def test_calls_out_raw_save_issue_as_violation(self) -> None:
        assert "Raw calls to `mcp__plugin_linear_linear__save_issue`" in (
            _CLAUDE_LINEAR_STANDARDS_RULE
        )

    def test_documents_numbered_list_workaround(self) -> None:
        assert "Numbered lists, not bulleted" in _CLAUDE_LINEAR_STANDARDS_RULE

    def test_documents_inline_code_workaround(self) -> None:
        assert "Inline-code file paths" in _CLAUDE_LINEAR_STANDARDS_RULE


class TestGenerateClaudeLinearStandardsRule:
    """File generation tests."""

    def test_creates_rule_file(self, tmp_path: Path) -> None:
        generate_claude_linear_standards_rule(tmp_path)
        target = tmp_path / ".claude" / "rules" / "linear-standards.md"
        assert target.exists()

    def test_creates_rules_directory(self, tmp_path: Path) -> None:
        generate_claude_linear_standards_rule(tmp_path)
        assert (tmp_path / ".claude" / "rules").is_dir()

    def test_returns_created_action(self, tmp_path: Path) -> None:
        result = generate_claude_linear_standards_rule(tmp_path)
        assert result["action"] == "created"

    def test_returns_updated_on_overwrite(self, tmp_path: Path) -> None:
        generate_claude_linear_standards_rule(tmp_path)
        result = generate_claude_linear_standards_rule(tmp_path)
        assert result["action"] == "updated"

    def test_result_contains_file_path(self, tmp_path: Path) -> None:
        result = generate_claude_linear_standards_rule(tmp_path)
        assert "file" in result
        assert "linear-standards.md" in result["file"]

    def test_written_content_matches_constant(self, tmp_path: Path) -> None:
        generate_claude_linear_standards_rule(tmp_path)
        written = (tmp_path / ".claude" / "rules" / "linear-standards.md").read_text(
            encoding="utf-8"
        )
        assert written == _CLAUDE_LINEAR_STANDARDS_RULE


class TestInitIntegration:
    """Verify tapps_init generates the linear-standards rule."""

    def test_init_generates_linear_standards_rule(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        result = bootstrap_pipeline(
            tmp_path,
            platform="claude",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "linear_standards_rule" in result
        rule_result = result["linear_standards_rule"]
        assert rule_result["action"] == "created"
        target = tmp_path / ".claude" / "rules" / "linear-standards.md"
        assert target.exists()


class TestUpgradeIntegration:
    """Verify tapps_upgrade regenerates the linear-standards rule."""

    def test_upgrade_regenerates_rule(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert "linear_standards_rule" in claude_result["components"]
        rule_result = claude_result["components"]["linear_standards_rule"]
        assert rule_result["action"] == "created"

    def test_upgrade_respects_skip_token(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        # upgrade_skip_files maps path-token strings, not artifact keys.
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - .claude/rules/linear-standards.md\n",
            encoding="utf-8",
        )

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert "skipped" in str(claude_result["components"]["linear_standards_rule"])
