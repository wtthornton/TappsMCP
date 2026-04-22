"""Integration tests for Epic 33.5: Upgrade path for corrected artifacts.

Verifies that ``tapps_upgrade`` regenerates ALL corrected artifacts from
Epic 33 stories: skills (33.1), subagents (33.2), path-scoped rules (33.3),
and permission rules (33.4).
"""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_old_style_skill(skills_dir: Path, name: str) -> None:
    """Create a skill file with old-style ``tools:`` frontmatter."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Old style.\n"
        f"tools: mcp__tapps-mcp__tapps_score_file\n---\n\nOld body.\n",
        encoding="utf-8",
    )


def _create_old_style_agent(agents_dir: Path, name: str) -> None:
    """Create an agent file without mcpServers or maxTurns."""
    (agents_dir / name).write_text(
        f"---\nname: {name.replace('.md', '')}\n"
        f"description: Old agent.\n"
        f"tools: Read, Glob\n---\n\nOld body.\n",
        encoding="utf-8",
    )


def _setup_claude_project(tmp_path: Path) -> None:
    """Create a minimal Claude Code project structure.

    Writes an empty ``pyproject.toml`` so the upgrade's Python-signal gate
    treats this as a Python project — these tests exercise the full rule
    bundle including ``python-quality.md``.
    """
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")


def _setup_cursor_project(tmp_path: Path) -> None:
    """Create a minimal Cursor project structure."""
    (tmp_path / ".cursor").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Tests: Skills get corrected frontmatter after upgrade
# ---------------------------------------------------------------------------


class TestUpgradeSkills:
    """Verify skills are regenerated with corrected frontmatter."""

    def test_skills_have_allowed_tools_after_upgrade(self, tmp_path: Path) -> None:
        """Old-style ``tools:`` skills get replaced with ``allowed-tools:``."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        _create_old_style_skill(skills_dir, "tapps-score")

        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result["success"] is True

        skill_content = (skills_dir / "tapps-score" / "SKILL.md").read_text(encoding="utf-8")
        assert "allowed-tools:" in skill_content
        assert "\ntools:" not in skill_content

    def test_skills_have_argument_hint_after_upgrade(self, tmp_path: Path) -> None:
        """Skills that need argument-hint get it after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        _create_old_style_skill(skills_dir, "tapps-score")

        upgrade_pipeline(tmp_path, platform="claude")

        skill_content = (skills_dir / "tapps-score" / "SKILL.md").read_text(encoding="utf-8")
        assert "argument-hint:" in skill_content

    def test_skills_updated_list_populated(self, tmp_path: Path) -> None:
        """Upgrade result reports skills as updated, not skipped."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        _create_old_style_skill(skills_dir, "tapps-score")
        _create_old_style_skill(skills_dir, "tapps-gate")

        result = upgrade_pipeline(tmp_path, platform="claude")
        platforms = result["components"]["platforms"]
        assert len(platforms) > 0
        claude_result = platforms[0]
        skills_info = claude_result["components"]["skills"]
        assert "tapps-score" in skills_info["updated"]
        assert "tapps-gate" in skills_info["updated"]

    def test_new_skills_created_during_upgrade(self, tmp_path: Path) -> None:
        """Skills that don't exist yet get created during upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        # Don't create any old skills - all should be created

        result = upgrade_pipeline(tmp_path, platform="claude")
        platforms = result["components"]["platforms"]
        claude_result = platforms[0]
        skills_info = claude_result["components"]["skills"]
        assert len(skills_info["created"]) >= 5  # At least 5 skills exist


# ---------------------------------------------------------------------------
# Tests: Subagents get corrected frontmatter after upgrade
# ---------------------------------------------------------------------------


class TestUpgradeSubagents:
    """Verify subagents are regenerated with corrected frontmatter."""

    def test_subagents_have_mcp_servers_after_upgrade(self, tmp_path: Path) -> None:
        """Old-style agents get ``mcpServers`` after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-reviewer.md")

        upgrade_pipeline(tmp_path, platform="claude")

        content = (agents_dir / "tapps-reviewer.md").read_text(encoding="utf-8")
        assert "mcpServers:" in content
        assert "tapps-mcp:" in content

    def test_subagents_have_max_turns_after_upgrade(self, tmp_path: Path) -> None:
        """Old-style agents get ``maxTurns`` after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-reviewer.md")

        upgrade_pipeline(tmp_path, platform="claude")

        content = (agents_dir / "tapps-reviewer.md").read_text(encoding="utf-8")
        assert "maxTurns:" in content

    def test_subagents_have_permission_mode_after_upgrade(self, tmp_path: Path) -> None:
        """Old-style agents get correct ``permissionMode`` after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-reviewer.md")

        upgrade_pipeline(tmp_path, platform="claude")

        content = (agents_dir / "tapps-reviewer.md").read_text(encoding="utf-8")
        assert "permissionMode:" in content

    def test_subagents_updated_list_populated(self, tmp_path: Path) -> None:
        """Upgrade result reports agents as updated."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-reviewer.md")

        result = upgrade_pipeline(tmp_path, platform="claude")
        platforms = result["components"]["platforms"]
        claude_result = platforms[0]
        agents_info = claude_result["components"]["agents"]
        assert "tapps-reviewer.md" in agents_info["updated"]

    def test_review_fixer_has_isolation_worktree(self, tmp_path: Path) -> None:
        """tapps-review-fixer agent has ``isolation: worktree`` after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        _create_old_style_agent(agents_dir, "tapps-review-fixer.md")

        upgrade_pipeline(tmp_path, platform="claude")

        content = (agents_dir / "tapps-review-fixer.md").read_text(encoding="utf-8")
        assert "isolation: worktree" in content


# ---------------------------------------------------------------------------
# Tests: Python quality rule generated after upgrade
# ---------------------------------------------------------------------------


class TestUpgradePythonQualityRule:
    """Verify path-scoped python-quality.md is created/updated."""

    def test_python_quality_rule_exists_after_upgrade(self, tmp_path: Path) -> None:
        """Upgrade creates ``.claude/rules/python-quality.md``."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")

        rule_path = tmp_path / ".claude" / "rules" / "python-quality.md"
        assert rule_path.exists()

    def test_python_quality_rule_has_paths_frontmatter(self, tmp_path: Path) -> None:
        """Rule file has ``paths:`` YAML frontmatter scoping to Python files."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")

        rule_path = tmp_path / ".claude" / "rules" / "python-quality.md"
        content = rule_path.read_text(encoding="utf-8")
        assert "paths:" in content
        assert '"**/*.py"' in content

    def test_python_quality_rule_updated_on_rerun(self, tmp_path: Path) -> None:
        """Rule is refreshed on subsequent upgrade runs."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        # First run creates it
        result1 = upgrade_pipeline(tmp_path, platform="claude")
        platforms1 = result1["components"]["platforms"]
        rule1 = platforms1[0]["components"]["python_quality_rule"]
        assert rule1["action"] == "created"

        # Second run updates it
        result2 = upgrade_pipeline(tmp_path, platform="claude")
        platforms2 = result2["components"]["platforms"]
        rule2 = platforms2[0]["components"]["python_quality_rule"]
        assert rule2["action"] == "updated"


# ---------------------------------------------------------------------------
# Tests: Permission rules in settings.json
# ---------------------------------------------------------------------------


class TestUpgradePermissionRules:
    """Verify ``.claude/settings.json`` gets permission entries."""

    def test_settings_json_has_permissions_after_upgrade(self, tmp_path: Path) -> None:
        """Upgrade creates settings.json with permission allow list."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")

        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        config = json.loads(settings_path.read_text(encoding="utf-8"))
        allow_list = config.get("permissions", {}).get("allow", [])
        assert "mcp__tapps-mcp" in allow_list
        assert "mcp__tapps-mcp__*" in allow_list

    def test_settings_json_preserves_existing_entries(self, tmp_path: Path) -> None:
        """Upgrade merges into existing settings without losing user entries."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        settings_path = tmp_path / ".claude" / "settings.json"
        existing = {"permissions": {"allow": ["Bash(git *)"]}, "customKey": True}
        settings_path.write_text(json.dumps(existing), encoding="utf-8")

        upgrade_pipeline(tmp_path, platform="claude")

        config = json.loads(settings_path.read_text(encoding="utf-8"))
        allow_list = config["permissions"]["allow"]
        assert "Bash(git *)" in allow_list
        assert "mcp__tapps-mcp" in allow_list
        assert config["customKey"] is True


# ---------------------------------------------------------------------------
# Tests: Dry run
# ---------------------------------------------------------------------------


class TestUpgradeDryRun:
    """Verify dry-run reports all artifact types without writing."""

    def test_dry_run_reports_all_claude_components(self, tmp_path: Path) -> None:
        """Dry run includes all Claude component types in the result."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        assert result["dry_run"] is True

        platforms = result["components"]["platforms"]
        assert len(platforms) > 0
        components = platforms[0]["components"]

        # All Epic 33 artifact types reported
        assert "skills" in components
        assert "agents" in components
        assert "python_quality_rule" in components
        assert "settings" in components

    def test_dry_run_does_not_write_skills(self, tmp_path: Path) -> None:
        """Dry run does not create skill files."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        skills_dir = tmp_path / ".claude" / "skills"
        assert not skills_dir.exists()

    def test_dry_run_preserves_custom_agents(self, tmp_path: Path) -> None:
        """Dry run lists non-tapps custom agents under ``preserved_files``.

        Confirms Ralph-style custom agents (e.g. ``ralph.md``) are reported
        as safe from the upgrade, not flagged for regeneration.
        """
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "ralph.md").write_text("custom ralph agent\n", encoding="utf-8")
        (agents_dir / "ralph-architect.md").write_text("custom\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        components = result["components"]["platforms"][0]["components"]

        agents = components["agents"]
        assert isinstance(agents, dict)
        assert agents["action"] == "would-write-managed-files"
        assert "ralph.md" in agents["preserved_files"]
        assert "ralph-architect.md" in agents["preserved_files"]
        assert all(name.startswith("tapps-") for name in agents["managed_files"])

    def test_dry_run_preserves_custom_skills(self, tmp_path: Path) -> None:
        """Dry run lists non-managed custom skills under ``preserved_skills``."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        (skills_dir / "ralph-custom").mkdir(parents=True, exist_ok=True)
        (skills_dir / "ralph-custom" / "SKILL.md").write_text("x\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        components = result["components"]["platforms"][0]["components"]

        skills = components["skills"]
        assert isinstance(skills, dict)
        assert skills["action"] == "would-write-managed-skills"
        assert "ralph-custom" in skills["preserved_skills"]
        assert "tapps-score" in skills["managed_skills"]

    def test_dry_run_hooks_signals_merge_not_overwrite(self, tmp_path: Path) -> None:
        """Dry run hooks entry documents the additive merge behavior."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        components = result["components"]["platforms"][0]["components"]

        hooks = components["hooks"]
        assert isinstance(hooks, dict)
        assert hooks["action"] == "would-write-managed-scripts"
        assert "merged by matcher" in hooks["note"]

    def test_dry_run_summary_has_verdict_for_clean_project(self, tmp_path: Path) -> None:
        """Clean project without custom files produces a ``review-recommended`` verdict.

        Greenfield projects hit ``CLAUDE.md`` / ``settings.json`` merge paths,
        so ``review-recommended`` is correct — there's content to inspect even
        if no managed file conflicts exist.
        """
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        assert "dry_run_summary" in result
        summary = result["dry_run_summary"]
        assert summary["verdict"] in {"safe-to-run", "review-recommended"}
        assert summary["managed_file_count"] > 0
        assert isinstance(summary["preserved_files"], list)
        assert isinstance(summary["review_recommended_for"], list)

    def test_dry_run_summary_lists_custom_preserved_files(
        self,
        tmp_path: Path,
    ) -> None:
        """Summary aggregates preserved files across agents and skills."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "ralph.md").write_text("x", encoding="utf-8")
        skills_dir = tmp_path / ".claude" / "skills"
        (skills_dir / "ralph-quickfix").mkdir(parents=True, exist_ok=True)
        (skills_dir / "ralph-quickfix" / "SKILL.md").write_text("x", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        summary = result["dry_run_summary"]
        preserved = summary["preserved_files"]
        assert any("ralph.md" in p for p in preserved)
        assert any("ralph-quickfix" in p for p in preserved)
        assert summary["preserved_file_count"] >= 2

    def test_dry_run_preserves_custom_ci_workflows(self, tmp_path: Path) -> None:
        """Dry run lists non-managed ``.github/workflows/`` files as preserved.

        The upgrade only writes ``codeql-analysis.yml``; other workflows
        (CI, release, etc.) stay untouched.
        """
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("custom ci\n", encoding="utf-8")
        (wf_dir / "release.yml").write_text("custom release\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        ci = result["components"]["ci_workflows"]
        assert isinstance(ci, dict)
        assert ci["action"] == "would-write-managed-files"
        assert "codeql-analysis.yml" in ci["managed_files"]
        assert "ci.yml" in ci["preserved_files"]
        assert "release.yml" in ci["preserved_files"]

    def test_dry_run_preserves_custom_github_templates(self, tmp_path: Path) -> None:
        """Dry run lists non-managed ``.github/`` entries as preserved.

        Covers both custom issue forms in ``.github/ISSUE_TEMPLATE/`` and
        root-level entries like ``CODEOWNERS`` / ``FUNDING.yml``.
        """
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        github_dir = tmp_path / ".github"
        github_dir.mkdir()
        (github_dir / "CODEOWNERS").write_text("@team\n", encoding="utf-8")
        it_dir = github_dir / "ISSUE_TEMPLATE"
        it_dir.mkdir()
        (it_dir / "security-vulnerability.yml").write_text("custom\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        tpl = result["components"]["github_templates"]
        assert isinstance(tpl, dict)
        assert tpl["action"] == "would-write-managed-files"
        assert "PULL_REQUEST_TEMPLATE.md" in tpl["managed_files"]
        assert "dependabot.yml" in tpl["managed_files"]
        assert any(m.startswith("ISSUE_TEMPLATE/") for m in tpl["managed_files"])
        assert "CODEOWNERS" in tpl["preserved_files"]
        assert "ISSUE_TEMPLATE/security-vulnerability.yml" in tpl["preserved_files"]

    def test_dry_run_summary_aggregates_github_artifacts(self, tmp_path: Path) -> None:
        """Summary rolls up repo-scope GitHub preserved files alongside platforms."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("x\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        summary = result["dry_run_summary"]
        assert any("ci_workflows/ci.yml" in p for p in summary["preserved_files"])
        # Managed count should include the 6 github_templates + 1 ci_workflow
        assert summary["managed_file_count"] >= 7

    def test_dry_run_summary_absent_on_live_run(self, tmp_path: Path) -> None:
        """Live (non-dry-run) invocations do not include ``dry_run_summary``."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        assert "dry_run_summary" not in result

    def test_dry_run_respects_skip_tokens(self, tmp_path: Path) -> None:
        """Dry run reports ``skipped`` for artifacts in ``upgrade_skip_files``."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - .claude/agents\n  - .claude/skills\n",
            encoding="utf-8",
        )

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        components = result["components"]["platforms"][0]["components"]

        assert components["agents"] == "skipped (upgrade_skip_files)"
        assert components["skills"] == "skipped (upgrade_skip_files)"


# ---------------------------------------------------------------------------
# Tests: Idempotency
# ---------------------------------------------------------------------------


class TestUpgradeIdempotent:
    """Verify upgrade is idempotent - running twice produces same result."""

    def test_idempotent_skills(self, tmp_path: Path) -> None:
        """Running upgrade twice produces identical skill files."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")
        skills_dir = tmp_path / ".claude" / "skills"
        first_contents: dict[str, str] = {}
        for skill_dir in skills_dir.iterdir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                first_contents[skill_dir.name] = skill_file.read_text(encoding="utf-8")

        upgrade_pipeline(tmp_path, platform="claude")
        for skill_dir in skills_dir.iterdir():
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                assert skill_file.read_text(encoding="utf-8") == first_contents[skill_dir.name]

    def test_idempotent_agents(self, tmp_path: Path) -> None:
        """Running upgrade twice produces identical agent files."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")
        agents_dir = tmp_path / ".claude" / "agents"
        first_contents: dict[str, str] = {}
        for agent_file in agents_dir.iterdir():
            first_contents[agent_file.name] = agent_file.read_text(encoding="utf-8")

        upgrade_pipeline(tmp_path, platform="claude")
        for agent_file in agents_dir.iterdir():
            assert agent_file.read_text(encoding="utf-8") == first_contents[agent_file.name]

    def test_idempotent_settings(self, tmp_path: Path) -> None:
        """Running upgrade twice produces identical settings.json."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        upgrade_pipeline(tmp_path, platform="claude")
        settings_path = tmp_path / ".claude" / "settings.json"
        first_content = settings_path.read_text(encoding="utf-8")

        upgrade_pipeline(tmp_path, platform="claude")
        assert settings_path.read_text(encoding="utf-8") == first_content


# ---------------------------------------------------------------------------
# Tests: Full end-to-end flow
# ---------------------------------------------------------------------------


class TestUpgradeEndToEnd:
    """End-to-end: old artifacts are replaced with corrected ones."""

    def test_full_upgrade_flow_claude(self, tmp_path: Path) -> None:
        """Init with old-style artifacts -> upgrade fixes everything."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        # Create old-style artifacts
        skills_dir = tmp_path / ".claude" / "skills"
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)

        for skill_name in ["tapps-score", "tapps-gate", "tapps-validate"]:
            _create_old_style_skill(skills_dir, skill_name)
        for agent_name in ["tapps-reviewer.md", "tapps-researcher.md", "tapps-validator.md"]:
            _create_old_style_agent(agents_dir, agent_name)

        # Run upgrade
        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result["success"] is True

        # Verify skills corrected
        for skill_name in ["tapps-score", "tapps-gate", "tapps-validate"]:
            content = (skills_dir / skill_name / "SKILL.md").read_text(encoding="utf-8")
            assert "allowed-tools:" in content or "mcp_tools:" in content
            assert content.startswith("---\n") or content.startswith("*Engagement")

        # Verify agents corrected
        for agent_name in ["tapps-reviewer.md", "tapps-researcher.md", "tapps-validator.md"]:
            content = (agents_dir / agent_name).read_text(encoding="utf-8")
            assert "mcpServers:" in content
            assert "maxTurns:" in content

        # Verify python quality rule
        rule_path = tmp_path / ".claude" / "rules" / "python-quality.md"
        assert rule_path.exists()
        rule_content = rule_path.read_text(encoding="utf-8")
        assert "paths:" in rule_content

        # Verify settings.json permissions
        settings_path = tmp_path / ".claude" / "settings.json"
        assert settings_path.exists()
        config = json.loads(settings_path.read_text(encoding="utf-8"))
        allow_list = config.get("permissions", {}).get("allow", [])
        assert "mcp__tapps-mcp" in allow_list

    def test_cursor_upgrade_creates_agents_and_skills(self, tmp_path: Path) -> None:
        """Cursor platform upgrade creates agents and skills."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_cursor_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="cursor")
        assert result["success"] is True

        # Verify cursor agents exist
        agents_dir = tmp_path / ".cursor" / "agents"
        assert agents_dir.exists()
        assert any(agents_dir.iterdir())

        # Verify cursor skills exist
        skills_dir = tmp_path / ".cursor" / "skills"
        assert skills_dir.exists()
        assert any(skills_dir.iterdir())
