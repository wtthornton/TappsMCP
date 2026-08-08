"""Tests for distribution.setup_upgrade_cli — upgrade output formatting and run_upgrade."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.distribution.setup_generator import (
    run_upgrade,
)


@pytest.fixture(autouse=True)
def _isolate_operator_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep tests off the developer machine's real ~/.local/bin MCP shims."""
    fake_home = tmp_path / "isolated-home"
    fake_home.mkdir()
    monkeypatch.setattr("tapps_mcp.distribution.setup_generator.Path.home", lambda: fake_home)
    monkeypatch.setattr(
        "tapps_mcp.distribution.blue_green.CURRENT_LINK",
        fake_home / ".tapps-mcp" / "current",
    )


class TestRunUpgrade:
    """Tests for the run_upgrade entry point."""

    def test_dry_run_no_file_changes(self, tmp_path, capsys):
        """dry_run=True should not create or modify files."""
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            result = run_upgrade(
                mcp_host="auto",
                project_root=str(tmp_path),
                dry_run=True,
            )
        assert result is True
        captured = capsys.readouterr()
        assert "DRY-RUN" in captured.out
        # AGENTS.md should not have been created
        assert not (tmp_path / "AGENTS.md").exists()

    def test_updates_agents_md_when_outdated(self, tmp_path, capsys):
        """run_upgrade updates AGENTS.md when it has an outdated version."""
        content = "<!-- tapps-agents-version: 0.0.1 -->\n# Old AGENTS\n\nOld content.\n"
        (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            run_upgrade(
                mcp_host="auto",
                project_root=str(tmp_path),
            )
        captured = capsys.readouterr()
        # The AGENTS.md section should report an update
        assert "AGENTS.md" in captured.out

    def test_agents_md_up_to_date(self, tmp_path, capsys):
        """run_upgrade reports up-to-date when AGENTS.md is current."""
        from tapps_mcp.prompts.prompt_loader import load_agents_template

        (tmp_path / "AGENTS.md").write_text(load_agents_template(), encoding="utf-8")
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            run_upgrade(
                mcp_host="auto",
                project_root=str(tmp_path),
            )
        captured = capsys.readouterr()
        assert "up-to-date" in captured.out

    def test_creates_agents_md_when_missing(self, tmp_path, capsys):
        """run_upgrade creates AGENTS.md when it does not exist."""
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            run_upgrade(
                mcp_host="auto",
                project_root=str(tmp_path),
            )
        assert (tmp_path / "AGENTS.md").exists()
        captured = capsys.readouterr()
        assert "AGENTS.md" in captured.out
        assert "created" in captured.out

    def test_emit_json_outputs_parseable_json_with_summary(self, tmp_path, capsys):
        """``emit_json=True`` writes valid JSON to stdout with the full dry-run dict.

        Verifies the 3.2.2 CLI addition: the precision work from 3.2.0/3.2.1
        is now accessible via ``tapps-mcp upgrade --json`` so CLI consumers
        get the same ``dry_run_summary`` + ``managed_files`` / ``preserved_files``
        lists that MCP tool callers already receive.
        """

        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            result = run_upgrade(
                mcp_host="claude-code",
                project_root=str(tmp_path),
                dry_run=True,
                emit_json=True,
            )
        assert result is True
        captured = capsys.readouterr()
        # stdout must be pure JSON — no text-summary artefacts like "DRY-RUN"
        assert "[DRY-RUN]" not in captured.out
        parsed = json.loads(captured.out)
        assert parsed["dry_run"] is True
        assert "dry_run_summary" in parsed
        assert parsed["dry_run_summary"]["verdict"] in {
            "safe-to-run",
            "review-recommended",
        }
        # AGENTS.md must not have been created under dry_run
        assert not (tmp_path / "AGENTS.md").exists()


class TestCliUpgrade:
    """Tests for the CLI upgrade command via Click's CliRunner."""

    def test_upgrade_help(self):
        """CLI upgrade --help works."""
        runner = CliRunner()
        result = runner.invoke(main, ["upgrade", "--help"])
        assert result.exit_code == 0
        assert "Refresh generated files" in result.output

    def test_upgrade_dry_run_via_cli(self, tmp_path):
        """CLI upgrade --dry-run does not create files."""
        runner = CliRunner()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            result = runner.invoke(
                main,
                ["upgrade", "--project-root", str(tmp_path), "--dry-run"],
            )
        assert result.exit_code == 0
        assert "DRY-RUN" in result.output
        # AGENTS.md should not have been created
        assert not (tmp_path / "AGENTS.md").exists()

    def test_upgrade_runs_successfully(self, tmp_path):
        """CLI upgrade creates expected files."""
        runner = CliRunner()
        with patch("tapps_mcp.distribution.setup_generator.Path.home", return_value=tmp_path):
            result = runner.invoke(
                main,
                ["upgrade", "--project-root", str(tmp_path)],
            )
        assert result.exit_code == 0
        assert "AGENTS.md" in result.output


# ---------------------------------------------------------------------------
# Story 47.1: Default scope is "project"
# ---------------------------------------------------------------------------


class TestUpgradeScope:
    """Tests for Epic 47.5 - upgrade command scope support."""

    def test_cli_upgrade_has_scope_option(self):
        """CLI upgrade command has --scope flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["upgrade", "--help"])
        assert result.exit_code == 0
        assert "--scope" in result.output

    def test_run_upgrade_accepts_scope(self, tmp_path):
        """run_upgrade accepts scope parameter without error."""
        with patch(
            "tapps_mcp.pipeline.upgrade.upgrade_pipeline",
            return_value={
                "success": True,
                "version": "0.8.0",
                "components": {},
                "errors": [],
            },
        ):
            ok = run_upgrade(
                mcp_host="claude-code",
                project_root=str(tmp_path),
                dry_run=True,
                scope="project",
            )
        assert ok


# ---------------------------------------------------------------------------
# Issue #80.2: env var migration across scopes
# ---------------------------------------------------------------------------
