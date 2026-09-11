"""Unit tests for the template artifact category (TAP-7423).

Split analogous to test_platform_project_scripts.py's sibling files — this
file covers the packaged asset itself plus generate_templates()/
plan_templates() behaviour. Pipeline (tapps_init/tapps_upgrade) wiring lives
in test_platform_templates_pipeline.py; the skip-token vocabulary lives in
test_platform_templates_skip_tokens.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_templates import (
    CLAUDE_TEMPLATES,
    CURSOR_TEMPLATES,
    ONE_PAGER_REL_PATH,
    generate_templates,
    load_one_pager_template,
    plan_templates,
)

_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}")


class TestPackagedTemplateLoads:
    def test_loads_nonempty_html(self) -> None:
        body = load_one_pager_template()
        assert body.strip()
        assert "<style>" in body

    def test_registry_points_at_the_same_relative_path(self) -> None:
        assert CLAUDE_TEMPLATES["one-pager"] == ONE_PAGER_REL_PATH
        assert CURSOR_TEMPLATES["one-pager"] == ONE_PAGER_REL_PATH
        assert ONE_PAGER_REL_PATH == "docs/templates/one-pager.html"


class TestBrandNeutrality:
    """Done-when item 6: no literal hex colour, no font-family literal."""

    def test_no_hex_color_literal(self) -> None:
        body = load_one_pager_template()
        hits = _HEX_COLOR_RE.findall(body)
        assert hits == [], f"hex colour literal(s) found: {hits}"

    def test_no_font_family_literal(self) -> None:
        body = load_one_pager_template()
        assert "font-family:" not in body

    def test_negative_control_hex_pattern_would_catch_a_real_hex(self) -> None:
        """Proves the regex isn't vacuously passing on this file's shape."""
        assert _HEX_COLOR_RE.findall("color: #ff00aa;") == ["#ff00aa"]

    def test_negative_control_font_family_pattern_would_catch_a_real_literal(self) -> None:
        css_rule = "h1 { font-family: Arial; }"
        assert "font-family:" in css_rule

    def test_carries_the_documented_token_contract(self) -> None:
        """The eleven token names a consumer must define are named in-file."""
        body = load_one_pager_template()
        for token in (
            "--bg",
            "--bg-alt",
            "--surface",
            "--border",
            "--fg",
            "--fg-dim",
            "--accent",
            "--accent-2",
            "--font",
            "--font-display",
            "--mono",
        ):
            assert token in body, f"token contract missing {token}"

    def test_no_nlt_labs_content(self) -> None:
        """Rejected-reuse item 3 context: this ships into client repos."""
        body = load_one_pager_template().lower()
        assert "nlt" not in body
        assert "new logic tech" not in body


class TestTemplateRegistryParity:
    """Done-when item 7: Claude and Cursor registries proven equal.

    CLAUDE_TEMPLATES/CURSOR_TEMPLATES are independent literals (matching the
    CLAUDE_SKILLS/CURSOR_SKILLS shape in platform_skills.py) — nothing but
    this test stops them from drifting.
    """

    def test_key_sets_match(self) -> None:
        assert set(CLAUDE_TEMPLATES) == set(CURSOR_TEMPLATES)

    def test_values_match(self) -> None:
        assert CLAUDE_TEMPLATES == CURSOR_TEMPLATES

    def test_negative_control_mismatched_dicts_would_fail(self) -> None:
        """Proves the equality assertion isn't vacuously true."""
        left = {"one-pager": "docs/templates/one-pager.html"}
        right = {"one-pager": "docs/templates/one-pager.html", "extra": "docs/templates/extra.html"}
        assert set(left) != set(right)


class TestGenerateTemplates:
    def test_creates_on_fresh_project(self, tmp_path: Path) -> None:
        result = generate_templates(tmp_path, "claude")
        assert result["templates"][ONE_PAGER_REL_PATH] == "created"
        assert result["overwrite_warnings"] == []
        written = tmp_path / ONE_PAGER_REL_PATH
        assert written.exists()
        assert written.read_text(encoding="utf-8") == load_one_pager_template()

    def test_unchanged_when_content_matches(self, tmp_path: Path) -> None:
        generate_templates(tmp_path, "claude")
        result = generate_templates(tmp_path, "claude")
        assert result["templates"][ONE_PAGER_REL_PATH] == "unchanged"

    def test_refreshed_and_warned_when_customized(self, tmp_path: Path) -> None:
        target = tmp_path / ONE_PAGER_REL_PATH
        target.parent.mkdir(parents=True)
        target.write_text("<!-- a customer's own copy -->", encoding="utf-8")

        result = generate_templates(tmp_path, "claude")

        assert result["templates"][ONE_PAGER_REL_PATH] == "refreshed"
        assert len(result["overwrite_warnings"]) == 1
        assert "one-pager.html" in result["overwrite_warnings"][0]
        assert target.read_text(encoding="utf-8") == load_one_pager_template()

    def test_cursor_platform_writes_same_path(self, tmp_path: Path) -> None:
        result = generate_templates(tmp_path, "cursor")
        assert result["templates"][ONE_PAGER_REL_PATH] == "created"
        assert (tmp_path / ONE_PAGER_REL_PATH).exists()

    @pytest.mark.parametrize("platform", ["claude", "cursor"])
    def test_written_file_has_no_leading_marker(self, tmp_path: Path, platform: str) -> None:
        """The written file is byte-identical to the packaged asset — no
        managed-block marker, no policy header (rejected-reuse reason 3)."""
        generate_templates(tmp_path, platform)
        content = (tmp_path / ONE_PAGER_REL_PATH).read_text(encoding="utf-8")
        assert "BEGIN: tapps-skill-asset" not in content
        assert content.startswith("<!--")


class TestPlanTemplates:
    def test_dry_run_reports_created_without_writing(self, tmp_path: Path) -> None:
        result = plan_templates(tmp_path, "claude")
        assert result["templates"][ONE_PAGER_REL_PATH] == "created"
        assert not (tmp_path / ONE_PAGER_REL_PATH).exists()

    def test_dry_run_reports_refreshed_without_writing_when_customized(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / ONE_PAGER_REL_PATH
        target.parent.mkdir(parents=True)
        target.write_text("customized", encoding="utf-8")

        result = plan_templates(tmp_path, "claude")

        assert result["templates"][ONE_PAGER_REL_PATH] == "refreshed"
        assert target.read_text(encoding="utf-8") == "customized"

    def test_dry_run_reports_unchanged_without_writing(self, tmp_path: Path) -> None:
        generate_templates(tmp_path, "claude")
        result = plan_templates(tmp_path, "claude")
        assert result["templates"][ONE_PAGER_REL_PATH] == "unchanged"
