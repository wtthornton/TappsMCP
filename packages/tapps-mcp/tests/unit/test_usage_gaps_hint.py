"""Tests for usage gap SessionStart hints (TAP-3578)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from tapps_mcp.tools.usage import format_session_start_gap_hint


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
