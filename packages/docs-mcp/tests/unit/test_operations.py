"""Tests for operational doc generators (runbook, postmortem)."""

from __future__ import annotations

from pathlib import Path

from docs_mcp.generators.operations import PostmortemGenerator, RunbookGenerator
from docs_mcp.generators.writing_principles import append_writing_principles


class TestWritingPrinciples:
    def test_append_once(self) -> None:
        base = "# Title\n\nBody.\n"
        out = append_writing_principles(base)
        assert "## Writing notes" in out
        assert out.count("## Writing notes") == 1


class TestRunbookGenerator:
    def test_generates_sections(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()
        (root / "pyproject.toml").write_text(
            '[project]\nname = "svc"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )
        content = RunbookGenerator().generate(
            root,
            title="Restart API",
            procedure="Check health\nRestart pod",
            escalation="Page on-call",
        )
        assert "# Runbook: Restart API" in content
        assert "## Procedure" in content
        assert "## Escalation" in content
        assert "Page on-call" in content
        assert "## Writing notes" in content


class TestPostmortemGenerator:
    def test_generates_sections(self, tmp_path: Path) -> None:
        root = tmp_path / "proj"
        root.mkdir()
        content = PostmortemGenerator().generate(
            root,
            title="Outage 2026-06-01",
            summary="API unavailable for 12 minutes.",
            root_cause="Config drift.",
        )
        assert "# Postmortem: Outage 2026-06-01" in content
        assert "## Summary" in content
        assert "API unavailable" in content
        assert "Config drift" in content


class TestDocsGenerateRunbook:
    async def test_success(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from docs_mcp.server_gen_tools import docs_generate_runbook
        from tests.helpers import make_settings

        root = tmp_path / "proj"
        root.mkdir()
        with patch(
            "docs_mcp.server_helpers._get_settings",
            return_value=make_settings(root),
        ):
            result = await docs_generate_runbook(
                title="Deploy",
                project_root=str(root),
            )
        assert result["success"] is True
        assert result["tool"] == "docs_generate_runbook"

    async def test_missing_title(self, tmp_path: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_runbook

        result = await docs_generate_runbook(title="")
        assert result["success"] is False
        assert result["error"]["code"] == "INPUT_INVALID"
