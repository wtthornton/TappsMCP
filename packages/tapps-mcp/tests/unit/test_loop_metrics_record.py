"""Stem coverage + smoke tests for loop_metrics_record (TAP-5606)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tapps_mcp.tools.loop_metrics_io import append_loop_metrics_row
from tapps_mcp.tools.loop_metrics_record import (
    count_consecutive_gate_skips,
    resolve_completion_gate_mode,
    resolve_project_root_from_payload,
)


def test_resolve_project_root_from_payload_prefers_project_dir(tmp_path: Path) -> None:
    root = resolve_project_root_from_payload({"project_dir": str(tmp_path)})
    assert root == tmp_path.resolve()


def test_count_consecutive_gate_skips(tmp_path: Path) -> None:
    append_loop_metrics_row(
        tmp_path,
        {
            "ts": 1,
            "files_edited": ["a.py"],
            "gate_skipped_files": ["a.py"],
            "checklist_called": False,
        },
    )
    assert count_consecutive_gate_skips(tmp_path) == 1


def test_resolve_completion_gate_mode_warn_default(tmp_path: Path) -> None:
    settings = SimpleNamespace(
        cursor_stop_completion_gate_resolved=lambda: "warn",
        ralph_mode=False,
        ralph_consecutive_skip_threshold=3,
    )
    assert resolve_completion_gate_mode(settings, tmp_path) == "warn"
