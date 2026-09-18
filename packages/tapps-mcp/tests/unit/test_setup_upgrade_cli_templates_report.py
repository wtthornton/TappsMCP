"""Reporter must surface the templates component's real outcome (TAP-7423 follow-up).

``pipeline.platform_templates.generate_templates`` returns
``{"templates": {rel_path: action}, "overwrite_warnings": [...]}`` — documented
in its own docstring. ``distribution.setup_upgrade_cli._echo_component_dict``
only ever looked at a top-level ``action`` key, which this shape never has, so
every templates run — created, refreshed, or unchanged — printed "already up
to date (skipped)". See /tmp/tmcp-r5-template-report.md for the full mechanism.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.setup_upgrade_cli import _echo_component_dict
from tapps_mcp.pipeline.platform_templates import generate_templates


class TestTemplatesComponentReportsCreated:
    """Negative control: a hand-built ``created`` result must not read as skipped."""

    def test_created_action_is_reported_not_skipped(self, capsys) -> None:
        value = {
            "templates": {"docs/templates/one-pager.html": "created"},
            "overwrite_warnings": [],
        }
        _echo_component_dict("templates", value)
        out = capsys.readouterr().out
        assert "already up to date" not in out.lower(), out
        assert "created" in out
        assert "docs/templates/one-pager.html" in out

    def test_refreshed_action_is_reported_not_skipped(self, capsys) -> None:
        value = {
            "templates": {"docs/templates/one-pager.html": "refreshed"},
            "overwrite_warnings": ["docs/templates/one-pager.html was customised"],
        }
        _echo_component_dict("templates", value)
        out = capsys.readouterr().out
        assert "already up to date" not in out.lower(), out
        assert "refreshed" in out
        assert "docs/templates/one-pager.html" in out

    def test_unchanged_action_still_reads_as_up_to_date(self, capsys) -> None:
        value = {
            "templates": {"docs/templates/one-pager.html": "unchanged"},
            "overwrite_warnings": [],
        }
        _echo_component_dict("templates", value)
        out = capsys.readouterr().out
        assert "unchanged" in out.lower() or "up to date" in out.lower()


class TestTemplatesEndToEnd:
    """Second control: feed the real producer's output straight into the reporter."""

    def test_fresh_project_reports_created_not_skipped(self, tmp_path: Path, capsys) -> None:
        assert not (tmp_path / "docs" / "templates").exists()
        result = generate_templates(tmp_path, "claude")
        assert result["templates"]["docs/templates/one-pager.html"] == "created"

        _echo_component_dict("templates", result)
        out = capsys.readouterr().out
        assert "already up to date" not in out.lower(), out
        assert "created" in out
