"""TAP-5551: usage_gaps flags AGENTS/CLAUDE edits without a follow-up doctor run.

Exercises the thin-agent gap through ``usage.compute_gaps`` *after*
:func:`tapps_mcp.tools.usage_thin_agent.install` has patched it in place —
TAP-5540 keeps the injection external to the ``usage.py`` megafile, so this
suite (not ``test_usage_gaps_hint.py``) owns the new-logic assertions and
scores cleanly on its own.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from tapps_mcp.tools import usage as usage_module
from tapps_mcp.tools.usage_thin_agent import install

install()


def _write_agents_edit(tmp_path: Path, *, tools_used: list[str]) -> None:
    metrics = tmp_path / ".tapps-mcp"
    metrics.mkdir(parents=True)
    (metrics / "loop-metrics.jsonl").write_text(
        json.dumps(
            {
                "ts": int(time.time()),
                "files_edited": ["AGENTS.md"],
                "gate_skipped_files": [],
                "lookup_docs_called": False,
                "checklist_called": False,
                "tools_used": tools_used,
            }
        )
        + "\n",
        encoding="utf-8",
    )


class TestThinAgentCheckSkipped:
    """``thin_agent_check_skipped`` fires when AGENTS/CLAUDE edits outrun doctor runs."""

    def test_fires_when_doctor_not_run(self, tmp_path: Path) -> None:
        _write_agents_edit(tmp_path, tools_used=["tapps_validate_changed"])
        report = usage_module.compute_gaps(tmp_path, called_tools={"tapps_session_start"})
        assert "thin_agent_check_skipped" in report["gaps"]
        assert any("AGENTS.md" in r and "tapps_doctor" in r for r in report["recommendations"])

    def test_clears_when_doctor_called_this_session(self, tmp_path: Path) -> None:
        _write_agents_edit(tmp_path, tools_used=["tapps_validate_changed"])
        report = usage_module.compute_gaps(
            tmp_path, called_tools={"tapps_session_start", "tapps_doctor"}
        )
        assert "thin_agent_check_skipped" not in report["gaps"]

    def test_clears_when_doctor_in_telemetry(self, tmp_path: Path) -> None:
        _write_agents_edit(tmp_path, tools_used=["tapps_doctor"])
        report = usage_module.compute_gaps(tmp_path, called_tools={"tapps_session_start"})
        assert "thin_agent_check_skipped" not in report["gaps"]

    def test_no_gap_without_agent_config_edits(self, tmp_path: Path) -> None:
        report = usage_module.compute_gaps(tmp_path, called_tools={"tapps_session_start"})
        assert "thin_agent_check_skipped" not in report["gaps"]
