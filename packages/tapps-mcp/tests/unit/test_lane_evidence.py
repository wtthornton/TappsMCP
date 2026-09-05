"""Tests for the claude -p lane-log evidence parser (TAP-6614)."""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.tools.lane_evidence import parse_lane_evidence

FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "lane_evidence" / "known_positive.jsonl"
)


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_normal_completion_returns_evidence(tmp_path: Path) -> None:
    """Known-positive fixture: a genuine evidence block at the end must be found."""
    result = parse_lane_evidence(FIXTURE)

    assert result["run_completed"] is True
    assert result["evidence_found"] is True
    assert result["evidence_fields"]["head_sha"] == "6d28346e28a5653d3720b5be26912ee5f08c1753"
    assert result["sentinel"] == "blocked"
    assert "--- LINEAR EVIDENCE ---" in result["evidence_block"]


def test_marker_in_prompt_echo_is_never_matched(tmp_path: Path) -> None:
    """The fixture's own prompt is echoed back as a tool_result (type == "user") and carries
    the literal marker as an unfilled template. Confirm the echo exists in the raw log (so this
    test would be vacuous otherwise), then confirm the parser's evidence came from the real
    completion, not the echoed template (which has no `head_sha=<real sha>` value).
    """
    rows = _rows(FIXTURE)
    echoed_rows = [
        row
        for row in rows
        if row.get("type") == "user"
        and "--- LINEAR EVIDENCE ---" in json.dumps(row.get("message", {}))
    ]
    assert echoed_rows, "fixture must contain a prompt echo carrying the marker"
    # The echoed template has an unfilled placeholder, never a real sha.
    assert "head_sha=<output" in json.dumps(echoed_rows[0]["message"])

    result = parse_lane_evidence(FIXTURE)

    assert result["evidence_fields"]["head_sha"] == "6d28346e28a5653d3720b5be26912ee5f08c1753"
    assert "head_sha=<output" not in (result["final_message"] or "")


def test_resumed_session_uses_last_result_event(tmp_path: Path) -> None:
    """A resumed session appends a second completed run to the same log; the LAST
    `type == "result"` event must win, not the first.
    """
    rows = _rows(FIXTURE)
    result_row = next(row for row in rows if row.get("type") == "result")

    second_run = dict(result_row)
    second_run["result"] = (
        "STATUS: resumed run complete\n\n"
        "--- LINEAR EVIDENCE ---\n"
        "head_sha=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "linear_write=not-attempted\n"
        "--- END EVIDENCE ---\n"
        "LANE-COMPLETE: done"
    )

    resumed_log = tmp_path / "resumed.log"
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    lines.append(json.dumps(second_run))
    resumed_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = parse_lane_evidence(resumed_log)

    assert result["evidence_found"] is True
    assert result["evidence_fields"]["head_sha"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert result["sentinel"] == "done"


def test_killed_mid_run_returns_evidence_found_false(tmp_path: Path) -> None:
    """A log with no `type == "result"` event (the lane was killed before finishing its turn)
    must report evidence_found=false explicitly, even though earlier partial assistant text
    exists in the log.
    """
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    # Drop the final `result` row — simulates the process being killed before it could emit one.
    killed_log = tmp_path / "killed_mid_run.log"
    killed_log.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")

    result = parse_lane_evidence(killed_log)

    assert result["run_completed"] is False
    assert result["evidence_found"] is False
    assert result["evidence_block"] is None


def test_missing_file_or_empty_log_is_not_evidence(tmp_path: Path) -> None:
    empty_log = tmp_path / "empty.log"
    empty_log.write_text("", encoding="utf-8")

    result = parse_lane_evidence(empty_log)

    assert result["run_completed"] is False
    assert result["evidence_found"] is False
    assert result["final_message"] is None
