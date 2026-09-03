"""Tests for the extracted handoff CLI group (covers cli_handoff)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from tapps_mcp.cli_handoff import handoff_group, handoff_write
from tapps_mcp.tools.handoff_schema import handoff_path


def test_handoff_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(handoff_group, ["--help"])
    assert result.exit_code == 0
    assert "write" in result.output


def test_handoff_write_requires_input() -> None:
    runner = CliRunner()
    result = runner.invoke(handoff_write, [], input="")
    assert result.exit_code == 2
    assert (
        "Provide --file" in result.output
        or "stdin" in result.output
        or "empty" in result.output.lower()
    )


def _handoff(program: str, *, updated: datetime | None = None, p0: str = "TAP-7008") -> str:
    stamp = (updated or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"""\
# Session handoff
**Program:** {program}
**Updated:** {stamp}
**Linear P0:** {p0}

## Done
- wired {program} to its surface

## Open
- none

## Next (P0)
- run the surfaces suite

## Success criterion
- the surface reaches the mechanism
"""


def _seed(project_root: Path, markdown: str) -> Path:
    path = handoff_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def _payload(output: str) -> Any:
    """Parse the JSON document out of mixed CLI output.

    Mirrors ``TestTheCliSurface._payload`` in test_handoff_surfaces.py: the
    JSON is the tail of the output, not the whole of it.
    """
    return json.loads(output[output.index("{") :])


class TestConflictAdvisoryOnTheCliSurface:
    """TAP-7008 — the CLI must speak the same conflict advisory the MCP path does."""

    def test_write_over_a_foreign_incumbent_names_the_archive_path_on_stderr(
        self, tmp_path: Path
    ) -> None:
        incumbent = _handoff("program-a")
        _seed(tmp_path, incumbent)

        result = CliRunner().invoke(
            handoff_write,
            ["--project-root", str(tmp_path), "--no-brain-mirror"],
            input=_handoff("program-b"),
        )

        assert result.exit_code == 0, result.output
        payload = _payload(result.output)
        assert payload["conflict_status"] == "overwritten"
        assert "warning: Replaced the handoff of program-a" in result.stderr
        archived_to = payload["conflict"]["archived_to"]
        assert archived_to in result.stderr
        assert Path(archived_to).read_text(encoding="utf-8") == incumbent

    def test_write_over_a_recent_unknown_incumbent_names_the_archive_path_on_stderr(
        self, tmp_path: Path
    ) -> None:
        """Header-less but freshly updated: TAP-7008's narrowed ``unknown`` case."""
        legacy = _handoff("program-a").replace("**Program:** program-a\n", "")
        _seed(tmp_path, legacy)

        result = CliRunner().invoke(
            handoff_write,
            ["--project-root", str(tmp_path), "--no-brain-mirror"],
            input=_handoff("program-b"),
        )

        assert result.exit_code == 0, result.output
        payload = _payload(result.output)
        assert payload["conflict_status"] == "unknown"
        assert "warning: Archived an incumbent handoff of unestablished ownership" in result.stderr
        archived_to = payload["conflict"]["archived_to"]
        assert archived_to in result.stderr

    def test_write_with_no_incumbent_emits_no_conflict_warning(self, tmp_path: Path) -> None:
        """Negative control: nothing to archive, nothing to warn about."""
        result = CliRunner().invoke(
            handoff_write,
            ["--project-root", str(tmp_path), "--no-brain-mirror"],
            input=_handoff("program-a"),
        )

        assert result.exit_code == 0, result.output
        payload = _payload(result.output)
        assert payload["conflict_status"] == "clear"
        assert "warning:" not in result.stderr

    def test_stdout_stays_parseable_when_a_conflict_warning_is_present(
        self, tmp_path: Path
    ) -> None:
        """The JSON document on stdout must still parse via the existing slice.

        structlog's own ``handoff_owner_conflict`` log line lands on stdout
        ahead of the JSON (the same interleaving ``TestTheCliSurface._payload``
        in test_handoff_surfaces.py already works around) — that producer is
        untouched by this change. What TAP-7008 adds is the prose advisory,
        and that must land on stderr only, never on stdout.
        """
        _seed(tmp_path, _handoff("program-a"))

        result = CliRunner().invoke(
            handoff_write,
            ["--project-root", str(tmp_path), "--no-brain-mirror"],
            input=_handoff("program-b"),
        )

        assert result.exit_code == 0, result.output
        assert "warning:" not in result.stdout
        payload = _payload(result.stdout)
        assert payload["conflict_status"] == "overwritten"

    def test_cli_conflict_status_matches_the_mcp_surface_for_the_same_record(
        self, tmp_path: Path
    ) -> None:
        """Same incumbent, same incoming write, two surfaces: one classification.

        The CLI and the MCP tool call the exact same
        :func:`~tapps_mcp.tools.handoff_guard.conflict_advisory`, so this pins
        that fact rather than asserting it by inspection. Kept synchronous:
        ``write_handoff_sync`` runs its own ``asyncio.run``, which cannot
        nest inside a pytest-asyncio test function's already-running loop, so
        the MCP half is driven through a fresh ``asyncio.run`` of its own
        instead.
        """
        import asyncio

        from tapps_mcp import server_pipeline_tools as spt

        cli_root = tmp_path / "cli"
        mcp_root = tmp_path / "mcp"
        cli_root.mkdir()
        mcp_root.mkdir()
        _seed(cli_root, _handoff("program-a"))
        _seed(mcp_root, _handoff("program-a"))

        cli_result = CliRunner().invoke(
            handoff_write,
            ["--project-root", str(cli_root), "--no-brain-mirror"],
            input=_handoff("program-b"),
        )
        assert cli_result.exit_code == 0, cli_result.output
        cli_payload = _payload(cli_result.output)

        with (
            patch("tapps_mcp.server_pipeline_tools.load_settings") as mock_settings,
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
        ):
            mock_settings.return_value.project_root = mcp_root
            mcp_result = asyncio.run(
                spt.tapps_handoff_save(_handoff("program-b"), mirror_brain=False)
            )

        assert mcp_result["data"]["conflict_status"] == cli_payload["conflict_status"]
        assert cli_payload["conflict_status"] == "overwritten"
