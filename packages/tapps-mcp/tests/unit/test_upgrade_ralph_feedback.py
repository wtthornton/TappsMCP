"""Tests for the Ralph-feedback upgrade opt-outs and gates.

Covers behavior added in response to external feedback from a bash-first,
publisher-style consumer:

- Language gate for Python-only rules (``python-quality.md``, ``tapps-pipeline.md``)
- ``.mcp.json`` consent gate (never implicitly opt a consumer in)
- ``AGENTS.md`` opt-out via sentinel and config flag
- Karpathy block opt-in at config level (never strips existing blocks)
- ``mcp_only`` narrow upgrade mode
- Per-artifact ``upgrade_skip_files`` tokens (CLAUDE.md no longer gates rules)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_mcp.pipeline.upgrade import (
    _ALL_SKIP_TOKENS,
    _agents_md_opt_out,
    _has_infra_signals,
    _has_python_signals,
    _mcp_json_has_tapps_entry,
    _skipped,
    upgrade_pipeline,
)


@pytest.fixture(autouse=True)
def _fresh_settings() -> None:
    """Drop any cached Settings so test-level env tweaks take effect."""
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _bash_project(tmp_path: Path) -> None:
    """Greenfield non-Python project with just a Claude Code shell."""
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)


def _python_project(tmp_path: Path) -> None:
    """Greenfield Python-project shape — pyproject marker + .claude."""
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_has_python_signals_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        assert _has_python_signals(tmp_path) is True

    def test_has_python_signals_py_file(self, tmp_path: Path) -> None:
        (tmp_path / "script.py").write_text("print('x')\n", encoding="utf-8")
        assert _has_python_signals(tmp_path) is True

    def test_has_python_signals_py_in_venv_ignored(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "x.py").write_text("", encoding="utf-8")
        assert _has_python_signals(tmp_path) is False

    def test_has_python_signals_requirements(self, tmp_path: Path) -> None:
        (tmp_path / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
        assert _has_python_signals(tmp_path) is True

    def test_has_python_signals_empty(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("bash project\n", encoding="utf-8")
        assert _has_python_signals(tmp_path) is False

    def test_has_infra_signals_dockerfile(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        assert _has_infra_signals(tmp_path) is True

    def test_has_infra_signals_compose_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "docker-compose.yaml").write_text("services: {}\n", encoding="utf-8")
        assert _has_infra_signals(tmp_path) is True

    def test_mcp_json_has_tapps_entry_missing_file(self, tmp_path: Path) -> None:
        assert _mcp_json_has_tapps_entry(tmp_path, "claude-code") is False

    def test_mcp_json_has_tapps_entry_no_entry(self, tmp_path: Path) -> None:
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"other": {"command": "x"}}}),
            encoding="utf-8",
        )
        assert _mcp_json_has_tapps_entry(tmp_path, "claude-code") is False

    def test_mcp_json_has_tapps_entry_present(self, tmp_path: Path) -> None:
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}),
            encoding="utf-8",
        )
        assert _mcp_json_has_tapps_entry(tmp_path, "claude-code") is True

    def test_mcp_json_has_tapps_entry_corrupt(self, tmp_path: Path) -> None:
        (tmp_path / ".mcp.json").write_text("{not json", encoding="utf-8")
        assert _mcp_json_has_tapps_entry(tmp_path, "claude-code") is False

    def test_agents_md_opt_out_disabled_flag(self, tmp_path: Path) -> None:
        assert (
            _agents_md_opt_out(tmp_path, create_flag=False)
            == "upgrade_create_agents_md=false"
        )

    def test_agents_md_opt_out_sentinel(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "# CLAUDE\n<!-- tapps:agents-md-disabled -->\nbody\n",
            encoding="utf-8",
        )
        reason = _agents_md_opt_out(tmp_path, create_flag=True)
        assert reason is not None
        assert "tapps:agents-md-disabled" in reason

    def test_agents_md_opt_out_no_signal(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE\nbody\n", encoding="utf-8")
        assert _agents_md_opt_out(tmp_path, create_flag=True) is None

    def test_skipped_respects_alias(self) -> None:
        assert _skipped("claude_md", {"CLAUDE.md"}) is True
        assert _skipped("claude_md", {".claude/settings.json"}) is False
        assert _skipped("karpathy", {"karpathy"}) is True

    def test_all_skip_tokens_includes_karpathy(self) -> None:
        assert "karpathy" in _ALL_SKIP_TOKENS
        assert ".mcp.json" in _ALL_SKIP_TOKENS
        assert ".claude/rules/python-quality.md" in _ALL_SKIP_TOKENS


# ---------------------------------------------------------------------------
# Language gate
# ---------------------------------------------------------------------------


class TestLanguageGate:
    def test_python_rule_skipped_on_bash_project(self, tmp_path: Path) -> None:
        _bash_project(tmp_path)
        result = upgrade_pipeline(tmp_path, platform="claude")
        claude = result["components"]["platforms"][0]
        assert claude["components"]["python_quality_rule"]["action"] == (
            "skipped (no python detected)"
        )
        assert not (tmp_path / ".claude" / "rules" / "python-quality.md").exists()

    def test_pipeline_rule_skipped_on_bash_project(self, tmp_path: Path) -> None:
        _bash_project(tmp_path)
        result = upgrade_pipeline(tmp_path, platform="claude")
        claude = result["components"]["platforms"][0]
        assert claude["components"]["pipeline_rule"]["action"] == (
            "skipped (no python or infra detected)"
        )

    def test_agent_scope_rule_still_installed_on_bash_project(self, tmp_path: Path) -> None:
        _bash_project(tmp_path)
        result = upgrade_pipeline(tmp_path, platform="claude")
        claude = result["components"]["platforms"][0]
        # agent-scope.md is universal and not gated by language
        scope = claude["components"]["agent_scope_rule"]
        assert isinstance(scope, dict) and scope.get("action") in ("created", "updated")
        assert (tmp_path / ".claude" / "rules" / "agent-scope.md").exists()

    def test_pipeline_rule_installed_when_dockerfile_present(self, tmp_path: Path) -> None:
        _bash_project(tmp_path)
        (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
        result = upgrade_pipeline(tmp_path, platform="claude")
        claude = result["components"]["platforms"][0]
        pipeline = claude["components"]["pipeline_rule"]
        assert isinstance(pipeline, dict) and pipeline.get("action") in ("created", "updated")

    def test_force_python_rule_overrides_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _bash_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_FORCE_PYTHON_QUALITY_RULE", "true")
        result = upgrade_pipeline(tmp_path, platform="claude")
        claude = result["components"]["platforms"][0]
        rule = claude["components"]["python_quality_rule"]
        assert isinstance(rule, dict) and rule.get("action") in ("created", "updated")


# ---------------------------------------------------------------------------
# .mcp.json consent gate
# ---------------------------------------------------------------------------


class TestMcpConsentGate:
    def test_greenfield_no_mcp_json_is_skipped(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        # No .mcp.json exists — consumer never opted in
        result = upgrade_pipeline(tmp_path, platform="claude")
        claude = result["components"]["platforms"][0]
        mcp = claude["components"]["mcp_config"]
        assert isinstance(mcp, dict)
        assert "skipped" in mcp["action"]
        assert "tapps_init" in mcp["hint"]
        # File must not be created behind the user's back
        assert not (tmp_path / ".mcp.json").exists()

    def test_existing_tapps_entry_triggers_regeneration(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        # User previously opted in but the entry is stale / malformed
        (tmp_path / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"tapps-mcp": {"command": "stale"}}}),
            encoding="utf-8",
        )
        result = upgrade_pipeline(tmp_path, platform="claude")
        claude = result["components"]["platforms"][0]
        # "ok" (validator accepted it) or "regenerated" (validator rejected it);
        # either is fine as long as we did NOT hit the consent-skip branch.
        assert claude["components"]["mcp_config"] != "skipped (upgrade_skip_files)"
        assert (
            claude["components"]["mcp_config"] in ("ok", "regenerated")
            or (
                isinstance(claude["components"]["mcp_config"], dict)
                and "skipped" not in claude["components"]["mcp_config"]["action"]
            )
        )

    def test_force_overrides_consent_gate(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        result = upgrade_pipeline(tmp_path, platform="claude", force=True)
        claude = result["components"]["platforms"][0]
        # With force=True the upgrade is allowed to create the entry even
        # though the consumer didn't opt in.
        assert claude["components"]["mcp_config"] in ("ok", "regenerated")
        assert (tmp_path / ".mcp.json").exists()


# ---------------------------------------------------------------------------
# AGENTS.md opt-out
# ---------------------------------------------------------------------------


class TestAgentsMdOptOut:
    def test_sentinel_in_claude_md_blocks_creation(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        (tmp_path / "CLAUDE.md").write_text(
            "# CLAUDE.md\n<!-- tapps:agents-md-disabled -->\nSource of truth.\n",
            encoding="utf-8",
        )
        result = upgrade_pipeline(tmp_path, platform="claude")
        agents = result["components"]["agents_md"]
        assert agents["action"] == "skipped"
        assert "tapps:agents-md-disabled" in agents["detail"]
        assert not (tmp_path / "AGENTS.md").exists()

    def test_config_flag_false_blocks_creation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_CREATE_AGENTS_MD", "false")
        result = upgrade_pipeline(tmp_path, platform="claude")
        agents = result["components"]["agents_md"]
        assert agents["action"] == "skipped"
        assert "upgrade_create_agents_md=false" in agents["detail"]
        assert not (tmp_path / "AGENTS.md").exists()

    def test_existing_agents_md_is_still_merged_when_opted_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        # User already has AGENTS.md — opting out must not regress merge
        (tmp_path / "AGENTS.md").write_text("# AGENTS\nUser content.\n", encoding="utf-8")
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_CREATE_AGENTS_MD", "false")
        result = upgrade_pipeline(tmp_path, platform="claude")
        agents = result["components"]["agents_md"]
        assert agents["action"] in ("merged", "up-to-date", "updated")
        # File still present
        assert (tmp_path / "AGENTS.md").exists()


# ---------------------------------------------------------------------------
# Karpathy block opt-in at config level
# ---------------------------------------------------------------------------


class TestKarpathyOptOut:
    def test_opt_out_does_not_install_new_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE\nHand-tuned content.\n", encoding="utf-8")
        monkeypatch.setenv("TAPPS_MCP_INCLUDE_KARPATHY_GUIDELINES", "false")
        result = upgrade_pipeline(tmp_path, platform="claude")
        kg = result["components"]["karpathy_guidelines"]
        assert kg["opted_out"] is True
        assert kg["files"]["CLAUDE.md"] == "skipped (opt-out)"
        # Verify the block was not added
        content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
        assert "BEGIN: karpathy-guidelines" not in content

    def test_opt_out_still_refreshes_existing_block(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        # Install the block first without opt-out
        from tapps_mcp.pipeline import karpathy_block
        from tapps_mcp.prompts.prompt_loader import load_karpathy_guidelines

        claude_md = tmp_path / "CLAUDE.md"
        seed = load_karpathy_guidelines()
        # Emulate a stale-SHA existing install by using a fake marker
        claude_md.write_text(
            "# CLAUDE\nUser.\n\n<!-- BEGIN: karpathy-guidelines deadbee -->\nstale\n"
            "<!-- END: karpathy-guidelines -->\n",
            encoding="utf-8",
        )
        # Sanity: block is present
        assert karpathy_block._find_block_span(
            claude_md.read_text(encoding="utf-8")
        ) is not None

        # Now opt out and run upgrade — the block must still refresh to current SHA
        monkeypatch.setenv("TAPPS_MCP_INCLUDE_KARPATHY_GUIDELINES", "false")
        result = upgrade_pipeline(tmp_path, platform="claude")
        kg = result["components"]["karpathy_guidelines"]
        assert kg["opted_out"] is True
        assert kg["files"]["CLAUDE.md"] in ("refreshed", "unchanged")
        assert seed.splitlines()[0] in claude_md.read_text(encoding="utf-8")

    def test_skip_token_karpathy_blocks_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", '["karpathy"]')
        result = upgrade_pipeline(tmp_path, platform="claude")
        kg = result["components"]["karpathy_guidelines"]
        assert kg["opted_out"] is True
        assert kg["files"]["CLAUDE.md"] == "skipped (opt-out)"


# ---------------------------------------------------------------------------
# mcp_only narrow upgrade
# ---------------------------------------------------------------------------


class TestMcpOnly:
    def test_mcp_only_skips_agents_md(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        result = upgrade_pipeline(tmp_path, platform="claude", mcp_only=True)
        assert result["components"]["agents_md"]["action"] == "skipped (mcp_only)"
        assert not (tmp_path / "AGENTS.md").exists()

    def test_mcp_only_skips_claude_md(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        result = upgrade_pipeline(tmp_path, platform="claude", mcp_only=True)
        claude = result["components"]["platforms"][0]
        assert "mcp_only_skipped" in claude["components"]
        skipped = claude["components"]["mcp_only_skipped"]["skipped"]
        assert "claude_md" in skipped
        assert "hooks" in skipped
        assert "agents" in skipped
        assert "skills" in skipped
        assert "python_quality_rule" in skipped

    def test_mcp_only_skips_karpathy(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        result = upgrade_pipeline(tmp_path, platform="claude", mcp_only=True)
        assert result["components"]["karpathy_guidelines"] == {"action": "skipped (mcp_only)"}

    def test_mcp_only_skips_github_artifacts(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        result = upgrade_pipeline(tmp_path, platform="claude", mcp_only=True)
        for key in ("ci_workflows", "github_copilot", "github_templates", "governance"):
            assert result["components"][key] == {"action": "skipped (mcp_only)"}

    def test_mcp_only_still_merges_settings_permissions(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        result = upgrade_pipeline(tmp_path, platform="claude", mcp_only=True, force=True)
        claude = result["components"]["platforms"][0]
        # settings.json permission merge still ran
        assert "settings" in claude["components"]
        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        allow = json.loads(settings_path.read_text(encoding="utf-8")).get(
            "permissions", {}
        ).get("allow", [])
        assert "mcp__tapps-mcp" in allow

    def test_mcp_only_no_rule_files_written(self, tmp_path: Path) -> None:
        _python_project(tmp_path)
        upgrade_pipeline(tmp_path, platform="claude", mcp_only=True)
        rules = tmp_path / ".claude" / "rules"
        assert not rules.exists() or not any(rules.iterdir())


# ---------------------------------------------------------------------------
# Per-artifact skip granularity — CLAUDE.md skip no longer gates everything
# ---------------------------------------------------------------------------


class TestPerArtifactSkipGranularity:
    def test_skip_claude_md_does_not_skip_hooks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        (tmp_path / "CLAUDE.md").write_text("# user CLAUDE\n", encoding="utf-8")
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", '["CLAUDE.md"]')
        result = upgrade_pipeline(tmp_path, platform="claude")
        claude = result["components"]["platforms"][0]
        # CLAUDE.md itself is skipped
        assert claude["components"]["claude_md"] == "skipped (upgrade_skip_files)"
        # But hooks/agents/skills/rules still run
        assert claude["components"]["hooks"] != "skipped (upgrade_skip_files)"
        assert claude["components"]["agents"] != "skipped (upgrade_skip_files)"
        assert claude["components"]["skills"] != "skipped (upgrade_skip_files)"
        assert claude["components"]["agent_scope_rule"] != "skipped (upgrade_skip_files)"

    def test_skip_rule_only(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _python_project(tmp_path)
        monkeypatch.setenv(
            "TAPPS_MCP_UPGRADE_SKIP_FILES",
            '[".claude/rules/python-quality.md"]',
        )
        result = upgrade_pipeline(tmp_path, platform="claude")
        claude = result["components"]["platforms"][0]
        assert claude["components"]["python_quality_rule"] == "skipped (upgrade_skip_files)"
        # agent_scope.md is independent
        scope = claude["components"]["agent_scope_rule"]
        assert not (isinstance(scope, str) and scope.startswith("skipped"))

    def test_unknown_skip_token_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _python_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", '["not_a_real_token"]')
        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result.get("unknown_skip_tokens") == ["not_a_real_token"]
