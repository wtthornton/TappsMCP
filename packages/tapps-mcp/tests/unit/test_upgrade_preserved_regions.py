"""TAP-7078 boxes 1, 2, 4: preserved_regions in the dry-run JSON, byte-identical
live upgrade below END, and host-mirror parity.

``enumerate_preserved`` (``upgrade_report.py``) is a whole-skill-directory
membership test: is this skill directory in the platform catalogue at all.
``orchestration-prompt`` is always in the catalogue
(``platform_skills.CLAUDE_SKILLS``/``CURSOR_SKILLS``), so a consumer's local
region *inside* its ``SKILL.md`` — below ``MARKER_END`` — could never be seen,
no matter how large it grew. ``plan_skills`` (``upgrade_host_context.py``) now
reports a per-skill ``preserved_regions`` line count distinct from
``preserved_skills``, and ``build_dry_run_summary``/``_absorb_component``
(``upgrade_report.py``) roll it up to the top level.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_mcp.pipeline.skill_managed_block import MARKER_END
from tapps_mcp.pipeline.upgrade import upgrade_pipeline

_LOCAL_REGION = (
    "\n\n<!-- tapps-skill-project-customizations: preserved -->\n\n"
    "Our own fleet manifest notes go here.\nSecond local line.\n"
)


@pytest.fixture(autouse=True)
def _fresh_settings() -> None:
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()


def _skill_md_paths(tmp_path: Path) -> tuple[Path, Path]:
    return (
        tmp_path / ".claude" / "skills" / "orchestration-prompt" / "SKILL.md",
        tmp_path / ".cursor" / "skills" / "orchestration-prompt" / "SKILL.md",
    )


def _append_local_region(path: Path) -> None:
    path.write_text(path.read_text(encoding="utf-8") + _LOCAL_REGION, encoding="utf-8")


def _below_end(content: str) -> str:
    idx = content.rfind(MARKER_END)
    assert idx != -1, "fixture must carry the managed-block END marker"
    return content[idx + len(MARKER_END) :]


class TestPreservedRegionsDryRunReporting:
    def test_dry_run_reports_preserved_regions_for_both_hosts(self, tmp_path: Path) -> None:
        _project(tmp_path)
        upgrade_pipeline(tmp_path, platform="both", dry_run=False)

        claude_md, cursor_md = _skill_md_paths(tmp_path)
        _append_local_region(claude_md)
        _append_local_region(cursor_md)

        result = upgrade_pipeline(tmp_path, platform="both", dry_run=True)

        summary = result["dry_run_summary"]
        assert summary["preserved_regions"].get("orchestration-prompt", 0) > 0

        claude_components = next(
            p for p in result["components"]["platforms"] if p["host"] == "claude-code"
        )["components"]
        cursor_components = next(
            p for p in result["components"]["platforms"] if p["host"] == "cursor"
        )["components"]
        assert claude_components["skills"]["preserved_regions"]["orchestration-prompt"] > 0
        assert cursor_components["skills"]["preserved_regions"]["orchestration-prompt"] > 0

    def test_no_local_region_reports_no_preserved_regions(self, tmp_path: Path) -> None:
        """Negative case: a fresh, untouched skill tree has nothing to report."""
        _project(tmp_path)
        upgrade_pipeline(tmp_path, platform="both", dry_run=False)

        result = upgrade_pipeline(tmp_path, platform="both", dry_run=True)
        assert "orchestration-prompt" not in result["dry_run_summary"]["preserved_regions"]


class TestLiveUpgradePreservesRegionByteIdentical:
    def test_live_upgrade_preserves_region_and_diffs_only_above_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _project(tmp_path)
        upgrade_pipeline(tmp_path, platform="both", dry_run=False)

        claude_md, cursor_md = _skill_md_paths(tmp_path)
        _append_local_region(claude_md)
        _append_local_region(cursor_md)
        pre_claude = claude_md.read_text(encoding="utf-8")
        pre_cursor = cursor_md.read_text(encoding="utf-8")
        pre_claude_below = _below_end(pre_claude)
        pre_cursor_below = _below_end(pre_cursor)

        # Negative control setup: change the upstream body (above END), never
        # the local region — a NO-OP upgrade proves nothing about preservation.
        import tapps_mcp.pipeline.platform_skills as platform_skills_mod

        original_body = platform_skills_mod.CLAUDE_SKILLS["orchestration-prompt"]
        changed_body = original_body + "\nExtra upstream line appended for this test.\n"
        monkeypatch.setitem(platform_skills_mod.CLAUDE_SKILLS, "orchestration-prompt", changed_body)
        monkeypatch.setitem(platform_skills_mod.CURSOR_SKILLS, "orchestration-prompt", changed_body)

        upgrade_pipeline(tmp_path, platform="both", dry_run=False)

        post_claude = claude_md.read_text(encoding="utf-8")
        post_cursor = cursor_md.read_text(encoding="utf-8")

        # The upstream change actually landed above END...
        assert "Extra upstream line appended for this test." in post_claude[: post_claude.rfind(MARKER_END)]
        assert "Extra upstream line appended for this test." in post_cursor[: post_cursor.rfind(MARKER_END)]
        # ...and the region below END is byte-identical to before the upgrade.
        assert _below_end(post_claude) == pre_claude_below
        assert _below_end(post_cursor) == pre_cursor_below
        # Mirror parity: both hosts carry the same local region.
        assert _below_end(post_claude) == _below_end(post_cursor)
