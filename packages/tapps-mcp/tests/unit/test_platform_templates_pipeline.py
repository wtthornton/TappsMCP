"""tapps_init / tapps_upgrade pipeline wiring for the template category (TAP-7423).

Mirrors test_platform_project_scripts_pipeline.py's shape for the analogous
project-root, host-agnostic scripts/ category.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.platform_templates import ONE_PAGER_REL_PATH, load_one_pager_template


class TestInitIntegration:
    def test_init_writes_one_pager_for_claude(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        result = bootstrap_pipeline(
            tmp_path,
            platform="claude",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert result["templates"]["templates"][ONE_PAGER_REL_PATH] == "created"
        written = tmp_path / ONE_PAGER_REL_PATH
        assert written.exists()
        assert written.read_text(encoding="utf-8") == load_one_pager_template()

    def test_init_writes_one_pager_for_cursor(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        result = bootstrap_pipeline(
            tmp_path,
            platform="cursor",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert result["templates"]["templates"][ONE_PAGER_REL_PATH] == "created"
        assert (tmp_path / ONE_PAGER_REL_PATH).exists()

    def test_init_minimal_does_not_write_template(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        result = bootstrap_pipeline(
            tmp_path,
            platform="claude",
            minimal=True,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert "templates" not in result
        assert not (tmp_path / ONE_PAGER_REL_PATH).exists()


class TestUpgradeIntegration:
    def _seed_minimal_project(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    def _claude_component(self, result: dict, name: str):
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        return claude_result["components"][name]

    def test_upgrade_writes_one_pager_live(self, tmp_path: Path) -> None:
        self._seed_minimal_project(tmp_path)

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        component = self._claude_component(result, "templates")
        assert component["templates"][ONE_PAGER_REL_PATH] == "created"
        assert (tmp_path / ONE_PAGER_REL_PATH).exists()

    def test_upgrade_refreshes_customized_one_pager_live(self, tmp_path: Path) -> None:
        self._seed_minimal_project(tmp_path)
        target = tmp_path / ONE_PAGER_REL_PATH
        target.parent.mkdir(parents=True)
        target.write_text("<!-- stale customer copy -->", encoding="utf-8")

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        component = self._claude_component(result, "templates")
        assert component["templates"][ONE_PAGER_REL_PATH] == "refreshed"
        assert len(component["overwrite_warnings"]) == 1
        assert target.read_text(encoding="utf-8") == load_one_pager_template()

    def test_dry_run_reports_would_write_without_writing(self, tmp_path: Path) -> None:
        self._seed_minimal_project(tmp_path)

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        component = self._claude_component(result, "templates")
        assert component["templates"][ONE_PAGER_REL_PATH] == "created"
        # Dry run must not actually write anything (Done-when item 3).
        assert not (tmp_path / ONE_PAGER_REL_PATH).exists()

    def test_dry_run_reports_refresh_without_writing_when_customized(self, tmp_path: Path) -> None:
        self._seed_minimal_project(tmp_path)
        target = tmp_path / ONE_PAGER_REL_PATH
        target.parent.mkdir(parents=True)
        target.write_text("customized", encoding="utf-8")

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        component = self._claude_component(result, "templates")
        assert component["templates"][ONE_PAGER_REL_PATH] == "refreshed"
        assert target.read_text(encoding="utf-8") == "customized"

    def test_upgrade_respects_templates_skip_token(self, tmp_path: Path) -> None:
        self._seed_minimal_project(tmp_path)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - docs/templates\n",
            encoding="utf-8",
        )

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        component = self._claude_component(result, "templates")
        assert "skipped" in str(component)
        assert not (tmp_path / ONE_PAGER_REL_PATH).exists()

    def test_cursor_upgrade_writes_one_pager_live(self, tmp_path: Path) -> None:
        (tmp_path / ".cursor").mkdir()
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="cursor", dry_run=False)
        platforms = result["components"]["platforms"]
        cursor_result = next(p for p in platforms if p["host"] == "cursor")
        assert cursor_result["components"]["templates"]["templates"][ONE_PAGER_REL_PATH] == (
            "created"
        )
        assert (tmp_path / ONE_PAGER_REL_PATH).exists()

    def test_cursor_upgrade_respects_templates_skip_token(self, tmp_path: Path) -> None:
        (tmp_path / ".cursor").mkdir()
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - docs/templates\n",
            encoding="utf-8",
        )
        target = tmp_path / ONE_PAGER_REL_PATH
        target.parent.mkdir(parents=True)
        target.write_text("<!-- stale customer copy -->", encoding="utf-8")
        mtime_before = target.stat().st_mtime_ns

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="cursor", dry_run=False)
        platforms = result["components"]["platforms"]
        cursor_result = next(p for p in platforms if p["host"] == "cursor")
        component = cursor_result["components"]["templates"]
        assert "skipped" in str(component)
        assert target.read_text(encoding="utf-8") == "<!-- stale customer copy -->"
        assert target.stat().st_mtime_ns == mtime_before
