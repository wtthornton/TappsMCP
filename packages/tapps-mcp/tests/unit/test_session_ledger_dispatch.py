"""Dispatch-seam tests for the per-session token/context-growth ledger (TAP-6615 round 2).

The seven tests in ``test_session_token_ledger.py`` drive
``record_tool_result_bytes``/``summarize_session_ledger`` directly with
hand-supplied integers -- a green suite over a path production never
reaches, per the independent verifier's refutation: ``record_tool_result_bytes``
had zero production call sites, so no real session ever wrote a ledger row.

Round 2's first pass wired the ledger into ``server._with_nudges``, but the
verifier found that seam bypassed by 10 of 45 registered tools (whichever
build their response via ``success_response``/``error_response`` and return
it directly). This module now drives the actual MCP dispatch path --
``mcp_register.register_tool`` -- the single point every registered tool's
handler passes through, so coverage is provable by enumeration rather than
by sampling one tool (``tapps_quick_check``).

``TestSessionLedgerDispatch`` exercises the real ``tapps_quick_check`` tool
through the real, fully-registered ``tapps_mcp.server.mcp`` instance (byte
sizes and telemetry must match a genuine response, not a stub).
``TestLedgerCoverageEnumeration`` builds a throwaway ``FastMCP`` instance,
registers a trivial stub under every one of the 45 canonical tool names via
the real ``register_tool``, and asserts each produces exactly one ledger
row -- proving the seam, not any one tool's business logic.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server import ALL_TOOL_NAMES
from tapps_mcp.server import mcp as _real_mcp
from tapps_mcp.tool_descriptions import TOOL_DESCRIPTIONS
from tapps_mcp.tools.usage import compute_gaps

_STUB_ANNOTATIONS = ToolAnnotations(readOnlyHint=True)


async def _call_tool(
    mcp_instance: FastMCP, name: str, arguments: dict[str, Any]
) -> types.CallToolResult:
    handler = mcp_instance._mcp_server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    return (await handler(request)).root


def _make_stub(name: str) -> Any:
    """A trivial handler registered under *name* -- exercises the seam, not
    any tool's real business logic."""

    async def _stub() -> dict[str, Any]:
        return {"success": True, "data": {}}

    _stub.__name__ = name
    return _stub


class TestSessionLedgerDispatch:
    """TAP-6615 round 2: the ledger is written from the single dispatch seam
    (``mcp_register.register_tool``), driven here through the real,
    fully-registered ``tapps_mcp.server.mcp`` instance.
    """

    @pytest.mark.asyncio
    async def test_quick_check_writes_ledger_line_with_real_byte_size(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real ``tapps_quick_check`` call, dispatched through the actual
        MCP tool-call handler, appends one ledger line whose ``bytes`` equals
        the length of the actual serialized response -- not a hand-supplied
        integer, unlike the seven unit tests that drive
        ``record_tool_result_bytes`` directly."""
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")

        call_result = await _call_tool(_real_mcp, "tapps_quick_check", {"file_path": str(f)})
        assert call_result.isError is not True
        result = call_result.structuredContent
        assert result is not None
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
            call_result = await _call_tool(_real_mcp, "tapps_quick_check", {"file_path": str(f)})

        assert call_result.isError is not True
        assert call_result.structuredContent["success"] is True
        assert ledger_path.is_dir()  # untouched -- the write failed, nothing was created
        mock_warning.assert_called_once()
        args, kwargs = mock_warning.call_args
        assert args[0] == "session_ledger.write_failed"
        assert kwargs["path"] == str(ledger_path)
        assert kwargs["tool"] == "tapps_quick_check"

    @pytest.mark.asyncio
    async def test_ledger_circular_reference_payload_is_logged_and_tool_still_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A self-referencing response dict must not propagate ``ValueError``
        out of the ledger seam: ``json.dumps`` now runs *inside*
        ``_record_ledger_entry``'s try (it previously ran before it, so a
        circular payload would have escaped despite the docstring promising
        it was swallowed). The failure is logged at warning level and
        swallowed, exactly like the unwritable-ledger-path case above."""
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        from tapps_mcp.server import _record_ledger_entry

        circular: dict[str, Any] = {"success": True, "data": {}}
        circular["data"]["self"] = circular

        mock_warning = MagicMock()
        with patch("tapps_mcp.server.logger.warning", mock_warning):
            _record_ledger_entry("tapps_quick_check", circular)  # must not raise

        ledger_path = tmp_path / ".tapps-mcp" / ".session-token-ledger.jsonl"
        assert not ledger_path.exists()  # the payload never serialized, nothing was written
        mock_warning.assert_called_once()
        args, kwargs = mock_warning.call_args
        assert args[0] == "session_ledger.write_failed"
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
            call_result = await _call_tool(_real_mcp, "tapps_quick_check", {"file_path": str(f)})
            assert call_result.isError is not True
            assert call_result.structuredContent["success"] is True

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

            call_result = await _call_tool(_real_mcp, "tapps_quick_check", {"file_path": str(f)})

            assert call_result.isError is not True
            assert call_result.structuredContent["success"] is True
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


class TestLedgerCoverageEnumeration:
    """Prove ledger coverage by enumeration over the canonical 45-tool
    registry (``server.ALL_TOOL_NAMES``), not by sampling one tool.

    Registers a trivial stub under every canonical name through the real
    ``register_tool`` seam on a throwaway ``FastMCP`` instance -- this
    exercises the dispatch wrapper itself, independent of any one tool's
    business logic or live-service dependencies (Linear, brain HTTP, etc.),
    per the round-2 instruction to use "a stubbed handler for tools needing
    live services".
    """

    @pytest.mark.asyncio
    async def test_every_registered_tool_appends_exactly_one_ledger_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        mcp_instance = FastMCP("LedgerCoverageEnumerationTest")
        for name in sorted(ALL_TOOL_NAMES):
            register_tool(mcp_instance, _make_stub(name), annotations=_STUB_ANNOTATIONS)

        for name in sorted(ALL_TOOL_NAMES):
            call_result = await _call_tool(mcp_instance, name, {})
            assert call_result.isError is not True, name

        ledger_path = tmp_path / ".tapps-mcp" / ".session-token-ledger.jsonl"
        rows = [
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").strip().splitlines()
        ]
        recorded_tools = [row["tool"] for row in rows]
        assert len(recorded_tools) == len(ALL_TOOL_NAMES) == 45, (
            f"expected exactly one ledger row per one of {len(ALL_TOOL_NAMES)} "
            f"registered tools, got {len(recorded_tools)}"
        )
        assert set(recorded_tools) == ALL_TOOL_NAMES
        assert len(recorded_tools) == len(set(recorded_tools)), "a tool was ledgered more than once"

    @pytest.mark.asyncio
    async def test_negative_control_bypassing_register_tool_drops_the_ledger_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Registering one tool straight on ``mcp_instance.tool()`` --
        bypassing ``register_tool``'s ledger wrapper -- must be visible in
        the enumeration: that tool's row disappears while every other tool's
        row is still present and named."""
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))
        bypassed = "tapps_score_file"
        mcp_instance = FastMCP("LedgerNegativeControlTest")
        for name in sorted(ALL_TOOL_NAMES):
            stub = _make_stub(name)
            if name == bypassed:
                mcp_instance.tool(
                    annotations=_STUB_ANNOTATIONS,
                    description=TOOL_DESCRIPTIONS[name],
                )(stub)
            else:
                register_tool(mcp_instance, stub, annotations=_STUB_ANNOTATIONS)

        for name in sorted(ALL_TOOL_NAMES):
            call_result = await _call_tool(mcp_instance, name, {})
            assert call_result.isError is not True, name

        ledger_path = tmp_path / ".tapps-mcp" / ".session-token-ledger.jsonl"
        rows = [
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").strip().splitlines()
        ]
        recorded_tools = {row["tool"] for row in rows}
        missing = ALL_TOOL_NAMES - recorded_tools
        assert missing == {bypassed}, (
            f"expected only the unwrapped registration ({bypassed!r}) to be "
            f"unledgered, got {sorted(missing)}"
        )
