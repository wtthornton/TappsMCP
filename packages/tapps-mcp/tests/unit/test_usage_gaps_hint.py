"""Tests for usage gap SessionStart hints (TAP-3578)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from tapps_mcp.tools.usage import compute_gaps, format_session_start_gap_hint


class TestComputeGapsScopedEdits:
    def test_tmp_scratch_excluded_from_edits_without_validation(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        loop_metrics = metrics_dir / "loop-metrics.jsonl"
        loop_metrics.write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": ["/tmp/snippet.py", str(tmp_path / "src/a.py")],
                    "gate_skipped_files": ["/tmp/snippet.py"],
                    "lookup_docs_called": False,
                    "checklist_called": False,
                    "tools_used": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(tmp_path, called_tools=set())
        assert "edits_without_validation" in report["gaps"]
        assert "/tmp/snippet.py" not in report["edited_files_recent"]
        assert str(tmp_path / "src/a.py") in report["edited_files_recent"]

    def test_recent_compliant_loops_suppress_recurring_skip_gap(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        now = int(time.time())
        rows = []
        for i in range(4):
            rows.append(
                {
                    "ts": now - i,
                    "files_edited": ["src/a.py"],
                    "gate_skipped_files": ["src/a.py"],
                    "lookup_docs_called": False,
                    "checklist_called": False,
                    "tools_used": [],
                }
            )
        for i in range(6):
            rows.append(
                {
                    "ts": now - 20 - i,
                    "files_edited": ["src/a.py"],
                    "gate_skipped_files": [],
                    "lookup_docs_called": True,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                }
            )
        (metrics_dir / "loop-metrics.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed", "tapps_checklist"},
        )
        assert "recurring_validation_skips" not in report["gaps"]

    def test_legacy_callmcptool_rows_excluded_from_recurring_skip(
        self, tmp_path: Path
    ) -> None:
        """Pre-TAP-4017 Cursor rows should not inflate gate-skip rate (TAP-4017)."""
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        now = int(time.time())
        src = str(tmp_path / "packages" / "mod.py")
        rows = []
        for i in range(8):
            rows.append(
                {
                    "ts": now - i,
                    "files_edited": [src, "/tmp/snippet.py"],
                    "gate_skipped_files": [src, "/tmp/snippet.py"],
                    "lookup_docs_called": False,
                    "checklist_called": False,
                    "tools_used": ["CallMcpTool", "Write", "Shell"],
                    "mcp_calls": 0,
                }
            )
        for i in range(2):
            rows.append(
                {
                    "ts": now - 20 - i,
                    "files_edited": [src],
                    "gate_skipped_files": [],
                    "lookup_docs_called": True,
                    "checklist_called": True,
                    "tools_used": ["tapps_validate_changed", "tapps_checklist"],
                    "mcp_calls": 2,
                }
            )
        (metrics_dir / "loop-metrics.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed", "tapps_checklist"},
        )
        assert "recurring_validation_skips" not in report["gaps"]


class TestFormatSessionStartGapHint:
    def test_returns_none_when_clean(self, tmp_path: Path) -> None:
        assert format_session_start_gap_hint(tmp_path) is None

    def test_surfaces_checklist_missing_from_violations(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        violations = metrics_dir / ".completion-gate-violations.jsonl"
        violations.write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "reasons": ["CHECKLIST_MISSING"],
                    "files_edited": ["src/a.py"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        hint = format_session_start_gap_hint(tmp_path)
        assert hint is not None
        assert "tapps_checklist" in hint

    def test_surfaces_loop_metric_gaps(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        loop_metrics = metrics_dir / "loop-metrics.jsonl"
        loop_metrics.write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": ["src/a.py"],
                    "mcp_calls": 1,
                    "gate_skipped_files": ["src/a.py"],
                    "lookup_docs_called": False,
                    "checklist_called": False,
                    "tools_used": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        hint = format_session_start_gap_hint(tmp_path)
        assert hint is not None
        assert "validation" in hint.lower() or "checklist" in hint.lower()
