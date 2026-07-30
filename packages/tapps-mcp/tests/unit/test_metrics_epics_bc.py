"""Tests for metrics epics B/C follow-ups (TAP-5272..5278)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.project.call_graph_cache import prune_call_graph_cache
from tapps_mcp.project.call_graph_types import CALL_GRAPH_CACHE_REL, CallGraphIndex
from tapps_mcp.tools.fleet_audit import run_fleet_audit
from tapps_mcp.tools.loop_metrics import (
    count_consecutive_gate_skips,
    resolve_completion_gate_mode,
)
from tapps_mcp.tools.usage import compute_gaps


class TestLookupDocsUnderusedTap5273:
    def test_flags_single_loop_with_uncached_external_lib(self, tmp_path: Path) -> None:
        """TAP-5273: one Python edit loop + external lib + no lookup → gap."""
        metrics = tmp_path / ".tapps-mcp"
        metrics.mkdir(parents=True)
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("import httpx\n", encoding="utf-8")
        (metrics / "loop-metrics.jsonl").write_text(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "files_edited": ["src/app.py"],
                    "lookup_docs_called": False,
                    "checklist_called": True,
                    "gate_skipped_files": [],
                    "tools_used": ["tapps_validate_changed"],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        report = compute_gaps(
            tmp_path,
            called_tools={"tapps_session_start", "tapps_validate_changed"},
        )
        assert "lookup_docs_underused" in report["gaps"]
        assert any("httpx" in r for r in report["recommendations"])


class TestRalphEscalateTap5274:
    def test_consecutive_skips_counted(self, tmp_path: Path) -> None:
        metrics = tmp_path / ".tapps-mcp"
        metrics.mkdir(parents=True)
        rows = []
        for i in range(3):
            rows.append(
                {
                    "ts": int(time.time()) - i,
                    "files_edited": [f"a{i}.py"],
                    "gate_skipped_files": [f"a{i}.py"],
                    "checklist_called": False,
                    "lookup_docs_called": False,
                    "tools_used": [],
                }
            )
        (metrics / "loop-metrics.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
        assert count_consecutive_gate_skips(tmp_path) == 3

    def test_ralph_mode_escalates_to_block(self, tmp_path: Path) -> None:
        metrics = tmp_path / ".tapps-mcp"
        metrics.mkdir(parents=True)
        rows = [
            {
                "ts": int(time.time()) - i,
                "files_edited": [f"a{i}.py"],
                "gate_skipped_files": [f"a{i}.py"],
                "checklist_called": False,
                "tools_used": [],
            }
            for i in range(3)
        ]
        (metrics / "loop-metrics.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
        settings = MagicMock()
        settings.cursor_stop_completion_gate_resolved.return_value = "warn"
        settings.ralph_mode = True
        settings.ralph_consecutive_skip_threshold = 3
        assert resolve_completion_gate_mode(settings, tmp_path) == "block"

    def test_interactive_stays_warn(self, tmp_path: Path) -> None:
        metrics = tmp_path / ".tapps-mcp"
        metrics.mkdir(parents=True)
        rows = [
            {
                "ts": int(time.time()),
                "files_edited": ["a.py"],
                "gate_skipped_files": ["a.py"],
                "checklist_called": False,
                "tools_used": [],
            }
        ]
        (metrics / "loop-metrics.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n",
            encoding="utf-8",
        )
        settings = MagicMock()
        settings.cursor_stop_completion_gate_resolved.return_value = "warn"
        settings.ralph_mode = False
        settings.ralph_consecutive_skip_threshold = 1
        assert resolve_completion_gate_mode(settings, tmp_path) == "warn"


class TestCallGraphCacheGcTap5276:
    def test_prune_empty_session_markers_dry_run(self, tmp_path: Path) -> None:
        tapps = tmp_path / ".tapps-mcp"
        tapps.mkdir(parents=True)
        marker = tapps / ".cursor-mcp-session-abc"
        marker.write_text("", encoding="utf-8")
        report = prune_call_graph_cache(tmp_path, dry_run=True)
        assert any(".cursor-mcp-session-abc" in p for p in report["would_remove"])  # type: ignore[operator]
        assert marker.exists()

    def test_prune_deletes_empty_marker(self, tmp_path: Path) -> None:
        tapps = tmp_path / ".tapps-mcp"
        tapps.mkdir(parents=True)
        marker = tapps / ".cursor-mcp-session-xyz"
        marker.write_text("", encoding="utf-8")
        report = prune_call_graph_cache(tmp_path, dry_run=False)
        assert not marker.exists()
        assert any("cursor-mcp-session-xyz" in p for p in report["removed"])  # type: ignore[operator]

    def test_prune_expired_index(self, tmp_path: Path) -> None:
        from tapps_mcp.project.call_graph_cache import save_call_graph_index

        save_call_graph_index(tmp_path, CallGraphIndex())
        cache = tmp_path / CALL_GRAPH_CACHE_REL
        # Make file look old
        old = time.time() - (30 * 24 * 3600)
        import os

        os.utime(cache, (old, old))
        report = prune_call_graph_cache(tmp_path, max_age_hours=1.0, dry_run=False)
        assert not cache.exists()
        assert report["removed"]


class TestFleetGateRollupTap5275:
    def test_gate_rollup_counts(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj_a"
        tapps = proj / ".tapps-mcp"
        (tapps / "metrics").mkdir(parents=True)
        (tapps / ".tapps-mcp.yaml").write_text("project_root: .\n", encoding="utf-8")
        # bootstrap marker used by discover — check what fleet uses
        (proj / ".tapps-mcp.yaml").write_text("x: 1\n", encoding="utf-8")
        (tapps / ".completion-gate-violations.jsonl").write_text(
            json.dumps({"ts": 1, "reasons": ["CHECKLIST_MISSING"]}) + "\n",
            encoding="utf-8",
        )
        (tapps / ".cache-gate-violations.jsonl").write_text(
            json.dumps({"ts": 1}) + "\n" + json.dumps({"ts": 2}) + "\n",
            encoding="utf-8",
        )
        (tapps / "loop-metrics.jsonl").write_text(
            json.dumps({"ts": 1, "files_edited": ["a.py"]}) + "\n",
            encoding="utf-8",
        )
        report = run_fleet_audit(roots=[proj], include_brain=False, period="7d")
        rollup = report["gate_rollup"]
        assert rollup["completion_gate_violations"] == 1
        assert rollup["cache_gate_violations"] == 2
        assert rollup["loop_metrics_rows"] == 1


class TestEngagementErrorCodeTap5278:
    @pytest.mark.asyncio
    async def test_invalid_level_records_error_code(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        recorded: list[dict[str, Any]] = []

        def _fake_record(tool: str, start: int, **kwargs: Any) -> None:
            recorded.append({"tool": tool, **kwargs})

        with patch("tapps_mcp.server._record_execution", side_effect=_fake_record):
            with patch("tapps_mcp.server._record_call"):
                result = tapps_set_engagement_level("nope")
        assert result["success"] is False
        assert result["error"]["code"] == "invalid_level"
        failed = [r for r in recorded if r.get("status") == "failed"]
        assert failed
        assert failed[0].get("error_code") == "invalid_level"


class TestBrainBridgeCloseTap5277:
    def test_placeholder_covered_in_test_brain_bridge_http(self) -> None:
        # Covered by TestHttpClose.test_close_on_closed_running_loop_uses_fresh_loop
        assert True
