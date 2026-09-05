"""Dispatch-seam tests for the per-session token/context-growth ledger (TAP-6615 round 2).

The seven tests in ``test_session_token_ledger.py`` drive
``record_tool_result_bytes``/``summarize_session_ledger`` directly with
hand-supplied integers -- a green suite over a path production never
reaches, per the independent verifier's refutation: ``record_tool_result_bytes``
had zero production call sites, so no real session ever wrote a ledger row.

These tests instead drive a real MCP tool (``tapps_quick_check``) through the
actual dispatch seam (``server._with_nudges`` / ``server._record_ledger_entry``)
and assert on the ledger file that results, kept in a separate module (rather
than appended to the already line-count-capped ``test_composite_tools.py``)
so the added integration coverage doesn't regress that megafile's
maintainability-index ratchet.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_scoring_tools import tapps_quick_check
from tapps_mcp.tools.usage import compute_gaps


class TestSessionLedgerDispatch:
    """TAP-6615 round 2: wire record_tool_result_bytes onto the real dispatch
    seam (server._with_nudges / server._record_ledger_entry) so the ledger
    the previous round shipped actually gets written from a real tool call.
    """

    @pytest.mark.asyncio
    async def test_quick_check_writes_ledger_line_with_real_byte_size(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real ``tapps_quick_check`` call appends one ledger line whose
        ``bytes`` equals the length of the actual serialized response --
        not a hand-supplied integer, unlike the seven unit tests that drive
        ``record_tool_result_bytes`` directly."""
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        result = await tapps_quick_check(str(f))

        assert result["success"] is True
        ledger_path = tmp_path / ".tapps-mcp" / ".session-token-ledger.jsonl"
        lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["tool"] == "tapps_quick_check"
        assert row["success"] is True
        assert row["bytes"] == len(json.dumps(result, default=str).encode("utf-8"))

    @pytest.mark.asyncio
    async def test_ledger_write_failure_is_logged_and_tool_still_succeeds(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An unwritable ledger path must not fail the tool: the ledger write
        is best-effort and the failure is logged at warning level with the
        ledger path (TAP-6615's "telemetry must never fail a tool"
        requirement). The ledger *file* path is made unwritable (occupied by
        a directory) rather than the whole ``.tapps-mcp/`` dir, so unrelated
        writers under that dir (recurring-quality-memory events, etc.) are
        unaffected and this test isolates the ledger write specifically.

        Asserts on ``server.logger.warning`` directly rather than ``caplog``:
        session-start logging setup (``bootstrap_logging_from_env`` ->
        ``root_logger.handlers.clear()``) can strip pytest's caplog handler
        mid-test, which would make a caplog assertion here order-dependent
        and flaky.
        """
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        ledger_path = tmp_path / ".tapps-mcp" / ".session-token-ledger.jsonl"
        ledger_path.mkdir(parents=True)  # occupy the ledger's own path with a directory

        mock_warning = MagicMock()
        with patch("tapps_mcp.server.logger.warning", mock_warning):
            result = await tapps_quick_check(str(f))

        assert result["success"] is True
        assert ledger_path.is_dir()  # untouched -- the write failed, nothing was created
        mock_warning.assert_called_once()
        args, kwargs = mock_warning.call_args
        assert args[0] == "session_ledger.write_failed"
        assert kwargs["path"] == str(ledger_path)
        assert kwargs["tool"] == "tapps_quick_check"

    @pytest.mark.asyncio
    async def test_usage_after_three_calls_reports_session_telemetry(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """tapps_usage, called after >=3 real tool calls, surfaces
        session_telemetry with the matching count and threshold guidance."""
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        for name in ("a", "b", "c"):
            f = tmp_path / f"{name}.py"
            f.write_text("x = 1\n", encoding="utf-8")
            result = await tapps_quick_check(str(f))
            assert result["success"] is True

        report = compute_gaps(tmp_path, called_tools={"tapps_quick_check"})

        assert "session_telemetry" in report
        telemetry = report["session_telemetry"]
        assert telemetry["tool_call_count"] == 3
        assert "estimated_context_growth_bytes" in telemetry
        assert "single_result_warn_kb" in telemetry
        assert "results_over_warn_threshold" in telemetry

    @pytest.mark.asyncio
    async def test_ledger_lands_under_linked_worktree_root_not_main_checkout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """From a real linked git worktree, the ledger must land under that
        worktree's own project root -- never scattered by the process cwd or
        collapsed into the main checkout's .tapps-mcp/ (the "must not
        scatter per-worktree" requirement TAP-6615 shipped unanswerable)."""
        repo_root = Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                check=True,
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parent,
            ).stdout.strip()
        )
        worktree_dir = tmp_path / "linked-worktree"
        branch_name = f"tap-6615-ledger-worktree-test-{tmp_path.name}"
        subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_dir), "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        try:
            monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(worktree_dir))
            f = worktree_dir / "test.py"
            f.write_text("x = 1\n", encoding="utf-8")

            result = await tapps_quick_check(str(f))

            assert result["success"] is True
            worktree_ledger = worktree_dir / ".tapps-mcp" / ".session-token-ledger.jsonl"
            main_ledger = repo_root / ".tapps-mcp" / ".session-token-ledger.jsonl"
            main_ledger_lines_before = (
                main_ledger.read_text(encoding="utf-8").count("\n") if main_ledger.exists() else 0
            )
            assert worktree_ledger.exists()
            assert "tapps_quick_check" in worktree_ledger.read_text(encoding="utf-8")
            # The worktree write must not have grown the main checkout's ledger.
            main_ledger_lines_after = (
                main_ledger.read_text(encoding="utf-8").count("\n") if main_ledger.exists() else 0
            )
            assert main_ledger_lines_after == main_ledger_lines_before
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_dir)],
                check=False,
                capture_output=True,
                text=True,
                cwd=repo_root,
            )
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                check=False,
                capture_output=True,
                text=True,
                cwd=repo_root,
            )
