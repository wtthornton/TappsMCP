"""Tests for linear-standards rule generation (TAP-980 Phase A).

Verifies that ``generate_claude_linear_standards_rule`` writes the expected
file, that the rule content documents the docs-mcp routing flow and the
Linear markdown workarounds, and that init / upgrade pipelines invoke it.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from tapps_mcp.pipeline.init_permissions import _NLT_PERMISSION_ENTRIES
from tapps_mcp.pipeline.platform_bundles import (
    _CLAUDE_LINEAR_STANDARDS_RULE,
    generate_claude_linear_standards_rule,
)

# Server keys this bundle actually ships an MCP entry for (TAP tmcp-r1r2:
# derived from the same _NLT_PERMISSION_ENTRIES list init_permissions.py
# grants tool access for — a rule token naming any other server names a
# server nothing creates). "plugin_linear_linear" is the one deliberate
# exception: a separate, independently-installed Linear plugin this bundle
# references but does not register.
_KNOWN_RULE_SERVERS = {
    entry.removeprefix("mcp__").removesuffix("__*")
    for entry in _NLT_PERMISSION_ENTRIES
    if entry.endswith("__*")
} | {"plugin_linear_linear"}


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return yaml.safe_load(parts[1]) or {}
    return {}


class TestRuleContent:
    """Inline content sanity checks — no file IO."""

    def test_always_apply(self) -> None:
        fm = _parse_frontmatter(_CLAUDE_LINEAR_STANDARDS_RULE)
        assert fm.get("alwaysApply") is False

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


class TestNoDeadNamespaceTokens:
    """TAP tmcp-r1r2: the docs-mcp / tapps-mcp server keys were retired when
    the six MCP servers were renamed to nlt-*; no shipped config registers
    either as a server key. A rule token naming them can never resolve."""

    def test_no_docs_mcp_tokens(self) -> None:
        assert _CLAUDE_LINEAR_STANDARDS_RULE.count("mcp__docs-mcp__") == 0

    def test_no_tapps_mcp_tokens(self) -> None:
        assert _CLAUDE_LINEAR_STANDARDS_RULE.count("mcp__tapps-mcp__") == 0

    def test_every_mcp_token_names_a_server_this_bundle_defines(self) -> None:
        """The check from the lane spec: a rule prose token must not restate
        a server name the bundle doesn't actually ship — the exact mismatch
        that let Defect A ship (the file's own comment already knew
        `mcp__docs-mcp__` resolves nothing, but the prose next to it still
        used it)."""
        tokens = set(re.findall(r"mcp__([A-Za-z0-9_-]+)__", _CLAUDE_LINEAR_STANDARDS_RULE))
        assert tokens, "expected at least one mcp__<server>__ token in the rule"
        unknown = tokens - _KNOWN_RULE_SERVERS
        assert not unknown, f"rule references undefined server(s): {sorted(unknown)}"


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

    def test_reports_always_apply_demotion(self, tmp_path: Path) -> None:
        """TAP-6987: the pre-existing file differs from the template, so the
        write is refused (``action: "diverged"``) — but the alwaysApply flip
        is still surfaced in the same report."""
        rules = tmp_path / ".claude" / "rules"
        rules.mkdir(parents=True)
        target = rules / "linear-standards.md"
        target.write_text(
            "---\nalwaysApply: true\n---\n# old\n",
            encoding="utf-8",
        )
        result = generate_claude_linear_standards_rule(tmp_path)
        assert result["action"] == "diverged"
        assert result.get("alwaysApply_demoted") is True
        assert result["alwaysApply_changed"] == {"from": True, "to": False}

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
