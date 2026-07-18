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
        _create_old_style_skill(skills_dir, "tapps-finish-task")

        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result["success"] is True

        skill_content = (skills_dir / "tapps-finish-task" / "SKILL.md").read_text(encoding="utf-8")
        assert "allowed-tools:" in skill_content
        assert "\ntools:" not in skill_content

    def test_skills_have_argument_hint_after_upgrade(self, tmp_path: Path) -> None:
        """Skills that need argument-hint get it after upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        _create_old_style_skill(skills_dir, "tapps-security")

        upgrade_pipeline(tmp_path, platform="claude")

        skill_content = (skills_dir / "tapps-security" / "SKILL.md").read_text(encoding="utf-8")
        assert "argument-hint:" in skill_content

    def test_skills_updated_list_populated(self, tmp_path: Path) -> None:
        """Upgrade result reports skills as updated, not skipped."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        _create_old_style_skill(skills_dir, "tapps-finish-task")
        _create_old_style_skill(skills_dir, "tapps-review-pipeline")

        result = upgrade_pipeline(tmp_path, platform="claude")
        platforms = result["components"]["platforms"]
        assert len(platforms) > 0
        claude_result = platforms[0]
        skills_info = claude_result["components"]["skills"]
        assert "tapps-finish-task" in skills_info["updated"]
        assert "tapps-review-pipeline" in skills_info["updated"]

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
# Tests: Doc-automation skills get refreshed on upgrade (not just init)
# ---------------------------------------------------------------------------


class TestUpgradeDocsAutomation:
    """Verify ``tapps_upgrade`` refreshes the doc-orchestration skills."""

    def test_docs_skills_created_on_claude_upgrade(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        # pyproject with a docs-mcp dep triggers detect_docsmcp.
        (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = ["docs-mcp"]\n',
            encoding="utf-8",
        )

        result = upgrade_pipeline(tmp_path, platform="claude")
        claude_result = result["components"]["platforms"][0]
        docs_info = claude_result["components"]["docs_automation"]
        assert isinstance(docs_info, dict)
        assert "tapps-docs-refresh" in docs_info["skills"]["created"]
        assert (tmp_path / ".claude" / "skills" / "tapps-docs-refresh" / "SKILL.md").is_file()

    def test_docs_skills_updated_on_cursor_upgrade(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        (tmp_path / ".cursor").mkdir(parents=True, exist_ok=True)
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\ndependencies = ["docs-mcp"]\n',
            encoding="utf-8",
        )
        # Pre-create a stale doc skill so the upgrade must overwrite it.
        stale = tmp_path / ".cursor" / "skills" / "tapps-docs-finish-task"
        stale.mkdir(parents=True, exist_ok=True)
        (stale / "SKILL.md").write_text("stale\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="cursor")
        cursor_result = result["components"]["platforms"][0]
        docs_info = cursor_result["components"]["docs_automation"]
        assert isinstance(docs_info, dict)
        assert "tapps-docs-finish-task" in docs_info["skills"]["updated"]
        refreshed = (stale / "SKILL.md").read_text(encoding="utf-8")
        assert refreshed != "stale\n"


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
        assert "nlt-build:" in content

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

        Confirms custom agents (e.g. ``custom-agent.md``) are reported
        as safe from the upgrade, not flagged for regeneration.
        """
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "custom-agent.md").write_text("custom agent\n", encoding="utf-8")
        (agents_dir / "custom-architect.md").write_text("custom\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        components = result["components"]["platforms"][0]["components"]

        agents = components["agents"]
        assert isinstance(agents, dict)
        assert agents["action"] == "would-write-managed-files"
        assert "custom-agent.md" in agents["preserved_files"]
        assert "custom-architect.md" in agents["preserved_files"]
        assert all(name.startswith("tapps-") for name in agents["managed_files"])

    def test_dry_run_preserves_custom_skills(self, tmp_path: Path) -> None:
        """Dry run lists non-managed custom skills under ``preserved_skills``."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        skills_dir = tmp_path / ".claude" / "skills"
        (skills_dir / "custom-skill").mkdir(parents=True, exist_ok=True)
        (skills_dir / "custom-skill" / "SKILL.md").write_text("x\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        components = result["components"]["platforms"][0]["components"]

        skills = components["skills"]
        assert isinstance(skills, dict)
        assert skills["action"] == "would-write-managed-skills"
        assert "custom-skill" in skills["preserved_skills"]
        assert "tapps-finish-task" in skills["managed_skills"]

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
        (agents_dir / "custom-agent.md").write_text("x", encoding="utf-8")
        skills_dir = tmp_path / ".claude" / "skills"
        (skills_dir / "custom-quickfix").mkdir(parents=True, exist_ok=True)
        (skills_dir / "custom-quickfix" / "SKILL.md").write_text("x", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        summary = result["dry_run_summary"]
        preserved = summary["preserved_files"]
        assert any("custom-agent.md" in p for p in preserved)
        assert any("custom-quickfix" in p for p in preserved)
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
        assert "dependabot.yml" not in tpl["managed_files"]
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

        for skill_name in ["tapps-finish-task", "tapps-review-pipeline", "tapps-handoff-session"]:
            _create_old_style_skill(skills_dir, skill_name)
        for agent_name in ["tapps-reviewer.md", "tapps-researcher.md", "tapps-validator.md"]:
            _create_old_style_agent(agents_dir, agent_name)

        # Run upgrade
        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result["success"] is True

        # Verify skills corrected
        for skill_name in ["tapps-finish-task", "tapps-review-pipeline", "tapps-handoff-session"]:
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


# ---------------------------------------------------------------------------
# TAP-2199: upgrade self-heals broken ${workspaceFolder} env block
# ---------------------------------------------------------------------------


class TestUpgradeWorkspaceFolderSelfHeal:
    """Existing consumers who installed before the TAP-2199 fix have
    ``${workspaceFolder}`` in their .mcp.json env block — Claude Code CLI
    won't expand it. The upgrade flow must detect and rewrite that value."""

    def _write_broken_cursor_config(self, project: Path) -> None:
        cursor_dir = project / ".cursor"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        broken = {
            "mcpServers": {
                "tapps-mcp": {
                    "type": "stdio",
                    "command": "tapps-mcp",
                    "args": ["serve"],
                    "env": {
                        "TAPPS_MCP_PROJECT_ROOT": "${workspaceFolder}",
                        "CUSTOM_KEY": "preserve-me",
                    },
                },
            },
        }
        (cursor_dir / "mcp.json").write_text(json.dumps(broken), encoding="utf-8")

    def test_dry_run_flags_broken_env_as_needs_heal(self, tmp_path: Path) -> None:
        """Dry-run reports the broken env as ``needs-heal`` with a TAP-2199 hint."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_cursor_project(tmp_path)
        self._write_broken_cursor_config(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="cursor", dry_run=True)
        platforms = result["components"]["platforms"]
        mcp_config = platforms[0]["components"]["mcp_config"]
        assert "needs-heal" in str(mcp_config)
        assert "TAP-2199" in str(mcp_config)

    def test_live_upgrade_rewrites_broken_env(self, tmp_path: Path) -> None:
        """A live upgrade rewrites the env block to the resolved project path."""
        from unittest.mock import MagicMock, patch

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_cursor_project(tmp_path)
        self._write_broken_cursor_config(tmp_path)

        no_drift = MagicMock(drift_detected=False)
        with patch("tapps_mcp.diagnostics.check_install_drift", return_value=no_drift):
            result = upgrade_pipeline(tmp_path, platform="cursor")
        platforms = result["components"]["platforms"]
        mcp_config = platforms[0]["components"]["mcp_config"]
        assert "healed" in str(mcp_config)

        from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

        data = _load_mcp_config_json(tmp_path / ".cursor" / "mcp.json")
        env = data["mcpServers"]["nlt-build"]["env"]
        assert env["TAPPS_MCP_PROJECT_ROOT"] == str(tmp_path.resolve())
        assert "${" not in env["TAPPS_MCP_PROJECT_ROOT"]
        assert env["CUSTOM_KEY"] == "preserve-me"

    def test_clean_config_reports_ok(self, tmp_path: Path) -> None:
        """A clean config (absolute path already) reports ``ok`` rather than healed."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_cursor_project(tmp_path)
        cursor_dir = tmp_path / ".cursor"
        good_servers = {
            sid: {
                "type": "stdio",
                "command": f".cursor/bin/{sid}-serve.sh",
                "args": [],
            }
            for sid in ("nlt-build", "nlt-memory", "nlt-linear-issues")
        }
        (cursor_dir / "mcp.json").write_text(
            json.dumps({"mcpServers": good_servers}),
            encoding="utf-8",
        )
        (tmp_path / ".tapps-mcp.yaml").write_text("mcp_bundle: developer\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="cursor")
        platforms = result["components"]["platforms"]
        mcp_config = platforms[0]["components"]["mcp_config"]
        assert mcp_config == "ok"

    def test_bundle_mismatch_syncs_mcp_config(self, tmp_path: Path) -> None:
        """Changing mcp_bundle in settings rewrites enabled servers on upgrade."""
        from unittest.mock import MagicMock, patch

        from tapps_mcp.distribution.setup_generator import _load_mcp_config_json
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_cursor_project(tmp_path)
        full_servers = {
            sid: {
                "type": "stdio",
                "command": f".cursor/bin/{sid}-serve.sh",
                "args": [],
            }
            for sid in (
                "nlt-build",
                "nlt-memory",
                "nlt-setup",
                "nlt-linear-issues",
                "nlt-project-docs",
                "nlt-release-ship",
            )
        }
        (tmp_path / ".cursor" / "mcp.json").write_text(
            json.dumps({"mcpServers": full_servers}),
            encoding="utf-8",
        )
        (tmp_path / ".tapps-mcp.yaml").write_text("mcp_bundle: developer\n", encoding="utf-8")

        no_drift = MagicMock(drift_detected=False)
        with patch("tapps_mcp.diagnostics.check_install_drift", return_value=no_drift):
            result = upgrade_pipeline(tmp_path, platform="cursor")
        mcp_config = result["components"]["platforms"][0]["components"]["mcp_config"]
        assert "synced" in str(mcp_config)
        assert "developer" in str(mcp_config)

        raw = (tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8")
        assert '"nlt-build"' in raw
        assert '"nlt-memory"' in raw
        assert '"nlt-linear-issues"' in raw
        assert "// Opt-in:" not in raw
        data = json.loads(raw)
        enabled = set(data["mcpServers"].keys())
        assert enabled == {"nlt-build", "nlt-memory", "nlt-linear-issues"}


# ---------------------------------------------------------------------------
# TECH_STACK.md — upgrade preserves existing, hints when missing
# ---------------------------------------------------------------------------


class TestUpgradeTechStackMd:
    """``TECH_STACK.md`` captures user tech choices, not tapps scaffolding.
    Upgrade preserves existing files and surfaces a hint when missing,
    so consumers know the artifact is known to the system without
    risking clobbering their content.
    """

    def test_existing_tech_stack_md_preserved(self, tmp_path: Path) -> None:
        """An existing TECH_STACK.md is never overwritten on upgrade."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        original = "# Custom Tech Stack\n\nPython 3.12, fastapi, custom-orm\n"
        (tmp_path / "TECH_STACK.md").write_text(original, encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude")
        component = result["components"]["tech_stack_md"]
        assert isinstance(component, dict)
        assert component["action"] == "preserved"
        assert (tmp_path / "TECH_STACK.md").read_text(encoding="utf-8") == original

    def test_missing_tech_stack_md_surfaces_hint(self, tmp_path: Path) -> None:
        """When TECH_STACK.md is missing, the report names the remediation path."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude")
        component = result["components"]["tech_stack_md"]
        assert isinstance(component, dict)
        assert component["action"] == "missing"
        assert "tapps-mcp init" in component["hint"]
        assert not (tmp_path / "TECH_STACK.md").exists()

    def test_skip_token_honored(self, tmp_path: Path) -> None:
        """``upgrade_skip_files: [TECH_STACK.md]`` short-circuits the handler."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files: [TECH_STACK.md]\n", encoding="utf-8"
        )

        result = upgrade_pipeline(tmp_path, platform="claude")
        component = result["components"]["tech_stack_md"]
        assert isinstance(component, dict)
        assert component["action"] == "skipped (upgrade_skip_files)"

    def test_mcp_only_skips(self, tmp_path: Path) -> None:
        """mcp_only mode short-circuits all platform-independent components."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        (tmp_path / "TECH_STACK.md").write_text("# custom\n", encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", mcp_only=True)
        component = result["components"]["tech_stack_md"]
        assert isinstance(component, dict)
        assert component["action"] == "skipped (mcp_only)"


# ---------------------------------------------------------------------------
# TAP-2334: CLAUDE.md version stamp + section-aware smart-merge
# ---------------------------------------------------------------------------


class TestUpgradeClaudeMdStamp:
    """End-to-end coverage for the CLAUDE.md stamp + smart-merge feature.

    Mirrors the AGENTS.md stamp tests: fresh write, version-match-skip,
    version-mismatch-merge, user-customization-preserved, and malformed-stamp
    tolerated.
    """

    def test_fresh_write_includes_stamp(self, tmp_path: Path) -> None:
        from tapps_mcp import __version__
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)

        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result["success"] is True
        claude_md = tmp_path / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text(encoding="utf-8")
        assert content.startswith(f"<!-- tapps-claude-version: {__version__} -->\n")

    def test_version_match_skips_merge(self, tmp_path: Path) -> None:
        """When the stamp matches, validation returns up-to-date and the merge
        path is not triggered (CLAUDE.md content unchanged beyond the Karpathy
        refresh)."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        upgrade_pipeline(tmp_path, platform="claude")
        claude_md = tmp_path / "CLAUDE.md"
        first = claude_md.read_text(encoding="utf-8")

        upgrade_pipeline(tmp_path, platform="claude")
        second = claude_md.read_text(encoding="utf-8")
        assert first == second

    def test_version_mismatch_triggers_merge(self, tmp_path: Path) -> None:
        """A stale stamp causes the upgrade to rewrite the obligations block
        and bump the stamp."""
        from tapps_mcp import __version__
        from tapps_mcp.pipeline.tapps_obligations_block import wrap_with_markers
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        _setup_claude_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "<!-- tapps-claude-version: 0.0.1 -->\n"
            + wrap_with_markers(load_platform_rules("claude"), version="0.0.1")
            + "\n",
            encoding="utf-8",
        )

        upgrade_pipeline(tmp_path, platform="claude")
        content = claude_md.read_text(encoding="utf-8")
        assert f"<!-- tapps-claude-version: {__version__} -->" in content
        assert "tapps-claude-version: 0.0.1" not in content
        assert f"<!-- BEGIN: tapps-obligations v{__version__} -->" in content

    def test_user_customizations_preserved_on_merge(self, tmp_path: Path) -> None:
        """User content outside the markered obligations block survives a
        stamp-bump merge."""
        from tapps_mcp.pipeline.tapps_obligations_block import wrap_with_markers
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        _setup_claude_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "<!-- tapps-claude-version: 0.0.1 -->\n"
            "# CLAUDE.md\n\n"
            "## Project Notes\n\n"
            "Custom guidance that must survive upgrade.\n\n"
            + wrap_with_markers(load_platform_rules("claude"), version="0.0.1")
            + "\n"
            "## Trailing Notes\n\nAlso keep.\n",
            encoding="utf-8",
        )

        upgrade_pipeline(tmp_path, platform="claude")
        content = claude_md.read_text(encoding="utf-8")
        assert "## Project Notes" in content
        assert "Custom guidance that must survive upgrade." in content
        assert "## Trailing Notes" in content
        assert "Also keep." in content

    def test_legacy_no_stamp_returns_needs_stamp(self, tmp_path: Path) -> None:
        """A CLAUDE.md without a stamp gets the stamp added without losing
        user content."""
        from tapps_mcp import __version__
        from tapps_mcp.pipeline.tapps_obligations_block import wrap_with_markers
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        _setup_claude_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "# CLAUDE.md\n\n"
            "## My Project\n\nUser content.\n\n"
            + wrap_with_markers(load_platform_rules("claude"), version="0.0.1")
            + "\n",
            encoding="utf-8",
        )

        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result["success"] is True
        content = claude_md.read_text(encoding="utf-8")
        assert content.startswith(f"<!-- tapps-claude-version: {__version__} -->\n")
        assert "## My Project" in content
        assert "User content." in content

    def test_malformed_stamp_tolerated(self, tmp_path: Path) -> None:
        """A non-semver stamp is treated as missing — upgrade prepends the
        canonical stamp without crashing on the malformed value."""
        from tapps_mcp import __version__
        from tapps_mcp.pipeline.tapps_obligations_block import wrap_with_markers
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        _setup_claude_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text(
            "<!-- tapps-claude-version: not-a-version -->\n"
            "# CLAUDE.md\n\n## User content\n\nKeep.\n\n"
            + wrap_with_markers(load_platform_rules("claude"), version="0.0.1")
            + "\n",
            encoding="utf-8",
        )

        result = upgrade_pipeline(tmp_path, platform="claude")
        assert result["success"] is True
        content = claude_md.read_text(encoding="utf-8")
        assert content.startswith(f"<!-- tapps-claude-version: {__version__} -->\n")
        assert "## User content" in content
        assert "Keep." in content

    def test_dry_run_reports_would_merge(self, tmp_path: Path) -> None:
        """Dry-run with a stale stamp surfaces ``would-merge`` and does not
        write to disk."""
        from tapps_mcp.pipeline.tapps_obligations_block import wrap_with_markers
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline
        from tapps_mcp.prompts.prompt_loader import load_platform_rules

        _setup_claude_project(tmp_path)
        claude_md = tmp_path / "CLAUDE.md"
        original = (
            "<!-- tapps-claude-version: 0.0.1 -->\n"
            + wrap_with_markers(load_platform_rules("claude"), version="0.0.1")
            + "\n"
        )
        claude_md.write_text(original, encoding="utf-8")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        platforms = result["components"]["platforms"]
        claude_md_status = platforms[0]["components"]["claude_md"]
        assert isinstance(claude_md_status, str)
        assert claude_md_status.startswith("would-merge")
        # File on disk untouched by the dry run.
        assert claude_md.read_text(encoding="utf-8") == original

    def test_dry_run_up_to_date(self, tmp_path: Path) -> None:
        """Dry-run on a fresh CLAUDE.md reports ``up-to-date``."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        upgrade_pipeline(tmp_path, platform="claude")

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        platforms = result["components"]["platforms"]
        claude_md_status = platforms[0]["components"]["claude_md"]
        assert claude_md_status == "up-to-date"


class TestUpgradeBrainMcpStrip:
    """TAP-1888: upgrade strips direct tapps-brain MCP entries."""

    def test_upgrade_strips_brain_mcp_from_project_config(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        _setup_claude_project(tmp_path)
        (tmp_path / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "tapps-mcp": {"command": "uv"},
                        "tapps-brain-mcp": {"command": "uv"},
                    }
                }
            ),
            encoding="utf-8",
        )

        result = upgrade_pipeline(tmp_path, platform="claude")
        strip_result = result["components"]["brain_mcp_strip"]
        assert ".mcp.json" in strip_result["stripped"]
        from tapps_mcp.distribution.setup_generator import _load_mcp_config_json

        updated = _load_mcp_config_json(tmp_path / ".mcp.json")
        assert "tapps-brain-mcp" not in updated["mcpServers"]
        assert "nlt-build" in updated["mcpServers"]
