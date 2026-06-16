"""Tests for cross-channel lookup telemetry (ADR-0021)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from tapps_mcp.tools.lookup_telemetry import (
    lookup_recorded_recently,
    record_lookup_event,
)


class TestLookupTelemetry:
    def test_record_and_detect_recent_lookup(self, tmp_path: Path) -> None:
        record_lookup_event(
            tmp_path,
            library="yaml",
            topic="safe_load",
            source="cli",
            resolved_library="pyyaml",
        )
        assert lookup_recorded_recently(tmp_path) is True

    def test_old_events_outside_window_ignored(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / ".tapps-mcp"
        metrics_dir.mkdir(parents=True)
        path = metrics_dir / ".lookup-docs-events.jsonl"
        path.write_text(
            json.dumps(
                {
                    "ts": int(time.time()) - 10 * 86_400,
                    "library": "fastapi",
                    "topic": "overview",
                    "source": "cli",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        assert lookup_recorded_recently(tmp_path, window_days=7) is False
