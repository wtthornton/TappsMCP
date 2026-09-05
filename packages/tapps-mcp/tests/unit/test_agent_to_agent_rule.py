"""Tests for agent-to-agent rule generation and doctor check (TAP-6886).

Verifies that ``generate_claude_agent_to_agent_rule`` writes the expected
file with the two load-bearing passages (§2 identity/authority, §5 the
two-failure-classes table) intact, that init / upgrade pipelines invoke it,
that ``agent_to_agent_rule`` is a recognized ``upgrade_skip_files`` token,
and that the doctor check reports both directions (missing/stale -> False,
current -> True).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from tapps_mcp.distribution.doctor_platform import check_agent_to_agent_rule
from tapps_mcp.pipeline.platform_bundles import (
    _CLAUDE_AGENT_TO_AGENT_RULE,
    generate_claude_agent_to_agent_rule,
)
from tapps_mcp.pipeline.upgrade_skip_tokens import (
    ALL_SKIP_TOKENS,
    SKIP_TOKENS,
    unknown_skip_tokens,
)

# The two load-bearing passages the source prompt forbids compressing.
IDENTITY_AUTHORITY_MARKER = "very likely the same human as you"
FAILURE_CLASSES_TABLE_MARKER = "Failure class | What catches it"


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return yaml.safe_load(parts[1]) or {}
    return {}


class TestRuleContent:
    """Inline content sanity checks — no file IO."""

    def test_always_apply_false(self) -> None:
        fm = _parse_frontmatter(_CLAUDE_AGENT_TO_AGENT_RULE)
        assert fm.get("alwaysApply") is False

    def test_covers_identity_and_authority_section(self) -> None:
        """§2 — must not be summarized away (lane brief, item 1)."""
        body = _CLAUDE_AGENT_TO_AGENT_RULE
        assert "## 2. Identity and authority" in body
        assert IDENTITY_AUTHORITY_MARKER in body
        assert "ls -ln /run/user/1000/cc-socks/<pid>.sock" in body
        assert "ps -o pid,user,lstart,args -p <pid>" in body

    def test_covers_failure_classes_table(self) -> None:
        """§5 — must not be summarized away (lane brief, item 2)."""
        body = _CLAUDE_AGENT_TO_AGENT_RULE
        assert "## 5. Epistemic protocol" in body
        assert FAILURE_CLASSES_TABLE_MARKER in body
        assert "Probe / measurement" in body
        assert "Prose / claim" in body

    def test_body_is_byte_identical_to_source_apart_from_frontmatter(self) -> None:
        source = Path("/tmp/agent-to-agent-source.md").read_text(encoding="utf-8")
        expected = "---\nalwaysApply: false\n---\n" + source
        assert expected == _CLAUDE_AGENT_TO_AGENT_RULE


class TestGenerateClaudeAgentToAgentRule:
    """File generation tests."""

    def test_creates_rule_file(self, tmp_path: Path) -> None:
        generate_claude_agent_to_agent_rule(tmp_path)
        assert (tmp_path / ".claude" / "rules" / "agent-to-agent.md").exists()

    def test_returns_created_action(self, tmp_path: Path) -> None:
        result = generate_claude_agent_to_agent_rule(tmp_path)
        assert result["action"] == "created"

    def test_returns_updated_on_overwrite(self, tmp_path: Path) -> None:
        generate_claude_agent_to_agent_rule(tmp_path)
        result = generate_claude_agent_to_agent_rule(tmp_path)
        assert result["action"] == "updated"

    def test_written_content_matches_constant(self, tmp_path: Path) -> None:
        generate_claude_agent_to_agent_rule(tmp_path)
        written = (tmp_path / ".claude" / "rules" / "agent-to-agent.md").read_text(encoding="utf-8")
        assert written == _CLAUDE_AGENT_TO_AGENT_RULE

    def test_regenerating_preserves_hand_edited_copy(self, tmp_path: Path) -> None:
        """TAP-6987: a diverged ``.claude/rules/*.md`` is never silently
        replaced — ``_write_claude_rule_file`` refuses the write and reports
        ``action: "diverged"`` instead, so the local edit survives."""
        rules = tmp_path / ".claude" / "rules"
        rules.mkdir(parents=True)
        (rules / "agent-to-agent.md").write_text("hand-edited nonsense\n", encoding="utf-8")
        result = generate_claude_agent_to_agent_rule(tmp_path)
        written = (rules / "agent-to-agent.md").read_text(encoding="utf-8")
        assert written == "hand-edited nonsense\n"
        assert result["action"] == "diverged"
        assert result["diverged"] is True
        assert "line_delta" in result

    def test_diverged_report_names_the_file_and_a_line_delta(self, tmp_path: Path) -> None:
        """Acceptance box 2 (TAP-6987): report file + line delta, not silence."""
        rules = tmp_path / ".claude" / "rules"
        rules.mkdir(parents=True)
        target = rules / "agent-to-agent.md"
        target.write_text("one\ntwo\n", encoding="utf-8")
        result = generate_claude_agent_to_agent_rule(tmp_path)
        assert result["file"] == str(target)
        assert re.fullmatch(r"\+\d+/-\d+", result["line_delta"])


class TestInitIntegration:
    """Verify tapps_init generates the agent-to-agent rule."""

    def test_init_generates_agent_to_agent_rule(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        result = bootstrap_pipeline(
            tmp_path,
            platform="claude",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "agent_to_agent_rule" in result
        assert result["agent_to_agent_rule"]["action"] == "created"
        assert (tmp_path / ".claude" / "rules" / "agent-to-agent.md").exists()


class TestUpgradeIntegration:
    """Verify tapps_upgrade restores and regenerates the agent-to-agent rule."""

    def test_upgrade_restores_deleted_copy(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert "agent_to_agent_rule" in claude_result["components"]
        assert claude_result["components"]["agent_to_agent_rule"]["action"] == "created"
        assert (tmp_path / ".claude" / "rules" / "agent-to-agent.md").exists()

    def test_upgrade_preserves_hand_edited_rule_without_skip_token(self, tmp_path: Path) -> None:
        """TAP-6987 acceptance box 3: a fixture project with a locally-edited
        ``.claude/rules/*.md`` survives ``upgrade_pipeline`` even with no
        ``upgrade_skip_files`` entry configured — divergence alone protects it."""
        (tmp_path / ".claude" / "rules").mkdir(parents=True)
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        edited = "LOCAL EDIT: do not clobber this\n"
        (tmp_path / ".claude" / "rules" / "agent-to-agent.md").write_text(
            edited, encoding="utf-8"
        )

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert claude_result["components"]["agent_to_agent_rule"]["action"] == "diverged"
        assert (
            tmp_path / ".claude" / "rules" / "agent-to-agent.md"
        ).read_text(encoding="utf-8") == edited

    def test_upgrade_respects_skip_token(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - .claude/rules/agent-to-agent.md\n",
            encoding="utf-8",
        )

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert "skipped" in str(claude_result["components"]["agent_to_agent_rule"])


class TestSkipTokenVocabulary:
    """Item 3 — agent_to_agent_rule must be a known token, both directions asserted."""

    def test_agent_to_agent_rule_is_a_known_token(self) -> None:
        assert "agent_to_agent_rule" in SKIP_TOKENS
        assert SKIP_TOKENS["agent_to_agent_rule"] == frozenset({".claude/rules/agent-to-agent.md"})
        assert ".claude/rules/agent-to-agent.md" in ALL_SKIP_TOKENS

    def test_known_token_not_reported_unknown(self) -> None:
        assert unknown_skip_tokens([".claude/rules/agent-to-agent.md"]) == []

    def test_known_bad_control_still_reported_unknown(self) -> None:
        """Negative control: a bad entry must still be flagged — proves the
        assertion above isn't vacuously true."""
        bad_entry = ".claude/rules/does-not-exist.md"
        assert unknown_skip_tokens([bad_entry]) == [bad_entry]


class TestDoctorCheck:
    """Item 4 — both directions asserted: missing/stale -> False, current -> True."""

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        result = check_agent_to_agent_rule(tmp_path)
        assert result.ok is False

    def test_stale_file_fails(self, tmp_path: Path) -> None:
        rules = tmp_path / ".claude" / "rules"
        rules.mkdir(parents=True)
        (rules / "agent-to-agent.md").write_text(
            "# Agent-to-Agent Communication\n\nStale content missing both load-bearing sections.\n",
            encoding="utf-8",
        )
        result = check_agent_to_agent_rule(tmp_path)
        assert result.ok is False

    def test_current_file_passes(self, tmp_path: Path) -> None:
        generate_claude_agent_to_agent_rule(tmp_path)
        result = check_agent_to_agent_rule(tmp_path)
        assert result.ok is True

    def test_check_is_registered_in_the_doctor_run(self, tmp_path: Path) -> None:
        """Registered in the spec list — an unwired check reports nothing."""
        from tapps_mcp.distribution.doctor_runner import _check_specs

        names = [name for name, _fn in _check_specs(tmp_path, quick=True)]
        assert "Agent-to-agent rule" in names
