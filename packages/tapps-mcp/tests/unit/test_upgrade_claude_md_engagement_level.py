"""TAP-7263: upgrade_claude_code must honour the declared engagement level.

``upgrade_host_claude.py`` called ``_bootstrap_claude`` without
``engagement_level``, so every upgrade silently re-stamped the ``medium``
template regardless of the project's declared ``llm_engagement_level`` —
``init_claude_md.py``'s own default. ``tapps_init``'s path
(``init_platform.py``) already threaded the real value through; this test
guards the now-fixed asymmetry on the ``upgrade`` path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_mcp.pipeline.tapps_obligations_block import MARKER_BEGIN_PREFIX, MARKER_END
from tapps_mcp.pipeline.upgrade import upgrade_pipeline


@pytest.fixture(autouse=True)
def _fresh_settings() -> None:
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _project(tmp_path: Path, *, engagement_level: str) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".tapps-mcp.yaml").write_text(
        f"llm_engagement_level: {engagement_level}\n", encoding="utf-8"
    )


def _obligations_block(claude_md: Path) -> str:
    content = claude_md.read_text(encoding="utf-8")
    begin = content.find(MARKER_BEGIN_PREFIX)
    assert begin != -1, "CLAUDE.md must carry the marker-wrapped obligations block"
    end = content.find(MARKER_END, begin)
    assert end != -1
    return content[begin : end + len(MARKER_END)]


class TestUpgradeHonoursEngagementLevel:
    def test_high_engagement_project_gets_high_template(self, tmp_path: Path) -> None:
        _project(tmp_path, engagement_level="high")

        upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        block = _obligations_block(tmp_path / "CLAUDE.md")
        block_lines = block.splitlines()
        # 168-line high template + 2 marker lines.
        assert len(block_lines) == 170
        assert "TAPPS Quality Pipeline - MANDATORY" in block
        assert "MUST follow" in block

    def test_medium_engagement_project_still_gets_medium_template(self, tmp_path: Path) -> None:
        """Positive control: proves the fix threads the real value through
        rather than hardcoding ``high`` for every project."""
        _project(tmp_path, engagement_level="medium")

        upgrade_pipeline(tmp_path, platform="claude", dry_run=False)

        block = _obligations_block(tmp_path / "CLAUDE.md")
        block_lines = block.splitlines()
        # 74-line medium template + 2 marker lines.
        assert len(block_lines) == 76
        assert "TAPPS Quality Pipeline - MANDATORY" not in block
