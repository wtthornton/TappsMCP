"""Tests for the per-session token/context-growth ledger (TAP-6615).

Telemetry only: these tests exercise ``record_tool_result_bytes`` /
``read_session_ledger`` (contract_telemetry.py) and
``summarize_session_ledger`` (usage.py) directly -- no gated tool's
behaviour is touched by this feature.
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.tools.contract_telemetry import (
    record_tool_result_bytes,
    read_session_ledger,
)
from tapps_mcp.tools.usage import compute_gaps, summarize_session_ledger


def test_record_tool_result_bytes_appends_one_line_per_call(tmp_path: Path) -> None:
    """The ledger file lives under .tapps-mcp/ and grows one JSONL row per call."""
    record_tool_result_bytes(tmp_path, tool_name="tapps_quick_check", byte_size=512)
    record_tool_result_bytes(tmp_path, tool_name="tapps_lookup_docs", byte_size=2048)

    ledger_path = tmp_path / ".tapps-mcp" / ".session-token-ledger.jsonl"
    lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()

    assert len(lines) == 2
    row = json.loads(lines[0])
    assert row["tool"] == "tapps_quick_check"
    assert row["bytes"] == 512
    assert row["source"] == "tool"


def test_read_session_ledger_returns_rows_in_order(tmp_path: Path) -> None:
    record_tool_result_bytes(tmp_path, tool_name="a", byte_size=10)
    record_tool_result_bytes(tmp_path, tool_name="b", byte_size=20)

    rows = read_session_ledger(tmp_path)

    assert [r["tool"] for r in rows] == ["a", "b"]


def test_summarize_session_ledger_reports_context_growth_and_subagent_split(
    tmp_path: Path,
) -> None:
    """Estimated context growth, tool-result bytes, and delegated subagent
    count/size are all surfaced from the ledger."""
    record_tool_result_bytes(tmp_path, tool_name="tapps_quick_check", byte_size=1000)
    record_tool_result_bytes(
        tmp_path, tool_name="Explore", byte_size=5000, source="subagent"
    )

    summary = summarize_session_ledger(tmp_path)

    assert summary is not None
    assert summary["tool_call_count"] == 2
    assert summary["estimated_context_growth_bytes"] == 6000
    assert summary["tool_result_bytes_ingested"] == 6000
    assert summary["subagent_result_count"] == 1
    assert summary["subagent_result_bytes"] == 5000


def test_summarize_session_ledger_flags_results_over_warn_threshold(tmp_path: Path) -> None:
    """tapps_usage output must surface threshold guidance: a single result
    bigger than the configurable KB limit is called out by name."""
    record_tool_result_bytes(tmp_path, tool_name="small", byte_size=100)
    record_tool_result_bytes(tmp_path, tool_name="huge", byte_size=50_000)

    summary = summarize_session_ledger(tmp_path, warn_kb=1)

    assert summary is not None
    assert summary["single_result_warn_kb"] == 1
    over = summary["results_over_warn_threshold"]
    assert len(over) == 1
    assert over[0]["tool"] == "huge"


def test_summarize_session_ledger_none_when_ledger_absent(tmp_path: Path) -> None:
    """Negative control: no ledger, no summary -- a fresh session's tapps_usage
    output stays uncluttered rather than reporting a zeroed-out block."""
    assert summarize_session_ledger(tmp_path) is None


def test_compute_gaps_surfaces_session_telemetry_when_ledger_present(tmp_path: Path) -> None:
    """The tapps_usage report (compute_gaps) includes session_telemetry once
    the ledger has entries, without requiring any gated-tool behaviour change."""
    (tmp_path / ".tapps-mcp").mkdir()
    record_tool_result_bytes(tmp_path, tool_name="tapps_quick_check", byte_size=300)

    report = compute_gaps(tmp_path, called_tools=set())

    assert "session_telemetry" in report
    assert report["session_telemetry"]["tool_call_count"] == 1


def test_compute_gaps_omits_session_telemetry_when_ledger_absent(tmp_path: Path) -> None:
    """Negative control: compute_gaps must not fabricate a telemetry block
    when nothing was ever recorded to the ledger."""
    report = compute_gaps(tmp_path, called_tools=set())

    assert "session_telemetry" not in report
