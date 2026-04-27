"""Tests for TAP-978 scoped quality rule generation.

Covers ``generate_claude_security_rule``, ``generate_claude_test_quality_rule``,
and ``generate_claude_config_files_rule`` — including init/upgrade integration
and per-rule skip-token honoring.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from tapps_mcp.pipeline.platform_bundles import (
    _CLAUDE_CONFIG_FILES_RULE,
    _CLAUDE_SECURITY_RULE,
    _CLAUDE_TEST_QUALITY_RULE,
    generate_claude_config_files_rule,
    generate_claude_security_rule,
    generate_claude_test_quality_rule,
)


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return yaml.safe_load(parts[1]) or {}
    return {}


class TestSecurityRuleContent:
    def test_path_scoped(self) -> None:
        fm = _parse_frontmatter(_CLAUDE_SECURITY_RULE)
        assert "paths" in fm
        assert any("security" in p for p in fm["paths"])

    def test_mentions_security_scan(self) -> None:
        assert "tapps_security_scan" in _CLAUDE_SECURITY_RULE

    def test_mentions_path_validator(self) -> None:
        assert "path_validator.py" in _CLAUDE_SECURITY_RULE


class TestTestQualityRuleContent:
    def test_path_scoped_to_tests(self) -> None:
        fm = _parse_frontmatter(_CLAUDE_TEST_QUALITY_RULE)
        assert "paths" in fm
        assert any("test" in p for p in fm["paths"])

    def test_mentions_pytest_fixtures(self) -> None:
        assert "pytest fixtures" in _CLAUDE_TEST_QUALITY_RULE

    def test_mentions_quick_check(self) -> None:
        assert "tapps_quick_check" in _CLAUDE_TEST_QUALITY_RULE


class TestConfigFilesRuleContent:
    def test_path_scoped_to_config_files(self) -> None:
        fm = _parse_frontmatter(_CLAUDE_CONFIG_FILES_RULE)
        paths = fm["paths"]
        assert any("yaml" in p for p in paths)
        assert any("Dockerfile" in p for p in paths)

    def test_mentions_validate_config(self) -> None:
        assert "tapps_validate_config" in _CLAUDE_CONFIG_FILES_RULE

    def test_mentions_docker_safety(self) -> None:
        assert "Pin base image versions" in _CLAUDE_CONFIG_FILES_RULE


class TestGenerators:
    def test_security_creates_file(self, tmp_path: Path) -> None:
        result = generate_claude_security_rule(tmp_path)
        target = tmp_path / ".claude" / "rules" / "security.md"
        assert target.exists()
        assert result["action"] == "created"
        assert "security.md" in result["file"]

    def test_security_idempotent(self, tmp_path: Path) -> None:
        generate_claude_security_rule(tmp_path)
        result = generate_claude_security_rule(tmp_path)
        assert result["action"] == "updated"

    def test_security_content_matches_constant(self, tmp_path: Path) -> None:
        generate_claude_security_rule(tmp_path)
        written = (tmp_path / ".claude" / "rules" / "security.md").read_text(encoding="utf-8")
        assert written == _CLAUDE_SECURITY_RULE

    def test_test_quality_creates_file(self, tmp_path: Path) -> None:
        result = generate_claude_test_quality_rule(tmp_path)
        assert (tmp_path / ".claude" / "rules" / "test-quality.md").exists()
        assert result["action"] == "created"

    def test_test_quality_idempotent(self, tmp_path: Path) -> None:
        generate_claude_test_quality_rule(tmp_path)
        result = generate_claude_test_quality_rule(tmp_path)
        assert result["action"] == "updated"

    def test_test_quality_content_matches_constant(self, tmp_path: Path) -> None:
        generate_claude_test_quality_rule(tmp_path)
        written = (tmp_path / ".claude" / "rules" / "test-quality.md").read_text(encoding="utf-8")
        assert written == _CLAUDE_TEST_QUALITY_RULE

    def test_config_files_creates_file(self, tmp_path: Path) -> None:
        result = generate_claude_config_files_rule(tmp_path)
        assert (tmp_path / ".claude" / "rules" / "config-files.md").exists()
        assert result["action"] == "created"

    def test_config_files_idempotent(self, tmp_path: Path) -> None:
        generate_claude_config_files_rule(tmp_path)
        result = generate_claude_config_files_rule(tmp_path)
        assert result["action"] == "updated"

    def test_config_files_content_matches_constant(self, tmp_path: Path) -> None:
        generate_claude_config_files_rule(tmp_path)
        written = (tmp_path / ".claude" / "rules" / "config-files.md").read_text(encoding="utf-8")
        assert written == _CLAUDE_CONFIG_FILES_RULE


class TestInitIntegration:
    def test_init_generates_all_three_rules(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        result = bootstrap_pipeline(
            tmp_path,
            platform="claude",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        for key, filename in (
            ("security_rule", "security.md"),
            ("test_quality_rule", "test-quality.md"),
            ("config_files_rule", "config-files.md"),
        ):
            assert key in result, f"init result missing {key}"
            rule_result = result[key]
            assert rule_result["action"] == "created"
            assert (tmp_path / ".claude" / "rules" / filename).exists()


class TestUpgradeIntegration:
    def _bootstrap_repo(self, tmp_path: Path, *, python: bool, infra: bool) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        if python:
            (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        if infra:
            (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    def test_upgrade_python_repo_regenerates_all_three(self, tmp_path: Path) -> None:
        self._bootstrap_repo(tmp_path, python=True, infra=False)

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        comps = claude_result["components"]
        for key in ("security_rule", "test_quality_rule", "config_files_rule"):
            assert isinstance(comps[key], dict), f"{key}: {comps[key]!r}"
            assert comps[key]["action"] == "created"

    def test_upgrade_infra_only_repo_skips_python_rules(self, tmp_path: Path) -> None:
        self._bootstrap_repo(tmp_path, python=False, infra=True)

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        comps = claude_result["components"]
        # Python-only rules skipped.
        assert "skipped" in str(comps["security_rule"])
        assert "skipped" in str(comps["test_quality_rule"])
        # Infra-or-python rule lands.
        assert isinstance(comps["config_files_rule"], dict)
        assert comps["config_files_rule"]["action"] == "created"

    def test_upgrade_bare_repo_skips_all_three(self, tmp_path: Path) -> None:
        self._bootstrap_repo(tmp_path, python=False, infra=False)

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        comps = claude_result["components"]
        for key in ("security_rule", "test_quality_rule", "config_files_rule"):
            assert "skipped" in str(comps[key]), f"{key}: {comps[key]!r}"

    def test_upgrade_respects_per_rule_skip_token(self, tmp_path: Path) -> None:
        self._bootstrap_repo(tmp_path, python=True, infra=False)
        # Per-token: skip just security.md, leave test-quality and config-files.
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - .claude/rules/security.md\n",
            encoding="utf-8",
        )

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        comps = claude_result["components"]
        assert comps["security_rule"] == "skipped (upgrade_skip_files)"
        assert isinstance(comps["test_quality_rule"], dict)
        assert comps["test_quality_rule"]["action"] == "created"
        assert isinstance(comps["config_files_rule"], dict)
        assert comps["config_files_rule"]["action"] == "created"

    def test_upgrade_dry_run_reports_all_three(self, tmp_path: Path) -> None:
        self._bootstrap_repo(tmp_path, python=True, infra=False)

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        comps = claude_result["components"]
        assert comps["security_rule"] == "would-regenerate"
        assert comps["test_quality_rule"] == "would-regenerate"
        assert comps["config_files_rule"] == "would-regenerate"
