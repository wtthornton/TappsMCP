"""tapps_init / tapps_upgrade pipeline wiring for project-root scripts (TAP-6884).

Split out from ``test_platform_project_scripts.py`` for gate size — see that
file's module docstring for why.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.platform_project_scripts import (
    GITFACTS_SH_REL_PATH,
    MEASURE_PY_REL_PATH,
)


class TestInitIntegration:
    def test_init_generates_both_scripts(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.init import bootstrap_pipeline

        result = bootstrap_pipeline(
            tmp_path,
            platform="claude",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        assert result["measure_script"]["action"] == "created"
        assert result["gitfacts_script"]["action"] == "created"
        assert (tmp_path / MEASURE_PY_REL_PATH).exists()
        assert (tmp_path / GITFACTS_SH_REL_PATH).exists()
        assert (tmp_path / MEASURE_PY_REL_PATH).stat().st_mode & 0o111
        assert (tmp_path / GITFACTS_SH_REL_PATH).stat().st_mode & 0o111


class TestUpgradeIntegration:
    def _seed_minimal_project(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# TAPPS Quality Pipeline\n")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    def test_upgrade_writes_both_scripts(self, tmp_path: Path) -> None:
        self._seed_minimal_project(tmp_path)

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert claude_result["components"]["measure_script"]["action"] == "created"
        assert claude_result["components"]["gitfacts_script"]["action"] == "created"
        assert (tmp_path / MEASURE_PY_REL_PATH).exists()
        assert (tmp_path / GITFACTS_SH_REL_PATH).exists()

    def test_upgrade_respects_measure_script_skip_token(self, tmp_path: Path) -> None:
        self._seed_minimal_project(tmp_path)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - scripts/measure.py\n",
            encoding="utf-8",
        )

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert "skipped" in str(claude_result["components"]["measure_script"])
        assert not (tmp_path / MEASURE_PY_REL_PATH).exists()
        # The sibling script is unaffected by the measure.py-scoped skip token.
        assert claude_result["components"]["gitfacts_script"]["action"] == "created"
        assert (tmp_path / GITFACTS_SH_REL_PATH).exists()

    def test_upgrade_respects_gitfacts_script_skip_token(self, tmp_path: Path) -> None:
        self._seed_minimal_project(tmp_path)
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "upgrade_skip_files:\n  - scripts/gitfacts.sh\n",
            encoding="utf-8",
        )

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=False)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert "skipped" in str(claude_result["components"]["gitfacts_script"])
        assert not (tmp_path / GITFACTS_SH_REL_PATH).exists()

    def test_dry_run_reports_would_regenerate(self, tmp_path: Path) -> None:
        self._seed_minimal_project(tmp_path)

        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)
        platforms = result["components"]["platforms"]
        claude_result = next(p for p in platforms if p["host"] == "claude-code")
        assert claude_result["components"]["measure_script"] == "would-regenerate"
        assert claude_result["components"]["gitfacts_script"] == "would-regenerate"
        # Dry run must not actually write anything.
        assert not (tmp_path / MEASURE_PY_REL_PATH).exists()
        assert not (tmp_path / GITFACTS_SH_REL_PATH).exists()
