"""Tests for TAP-7019: obligations stated conditionally, not as blanket assertions.

``recommended_next`` (server_pipeline_tools.py) and ``CHECKLIST_SKIPPED_REC``
(agent_contract.py) used to read as unconditional commands ("after each
edit") regardless of what the turn actually touched. This exercises the
conditional wording plus the underlying gate they describe: a turn that
edits only non-scorable files (docs/shell/config) is not counted as an
obligation miss, while a turn that genuinely uses a library API without a
lookup is still flagged (negative control) -- reusing the existing
``source_profile`` / scoped-source-edit gating from TAP-7016 (PR #358),
not reimplementing it.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.agent_contract import CHECKLIST_SKIPPED_REC
from tapps_mcp.server_pipeline_tools import SESSION_START_QUICK_RECOMMENDED_NEXT
from tapps_mcp.tools.usage import compute_gaps


def test_recommended_next_is_conditional_on_scorable_edit() -> None:
    """The session-start reminder must name the condition, not just the action."""
    assert "scorable" in SESSION_START_QUICK_RECOMMENDED_NEXT.lower()


def test_checklist_skipped_rec_is_conditional_on_scorable_edit() -> None:
    assert "scorable" in CHECKLIST_SKIPPED_REC.lower()


def _write_loop_metrics(tmp_path: Path, row: str) -> None:
    metrics = tmp_path / ".tapps-mcp"
    metrics.mkdir(parents=True, exist_ok=True)
    (metrics / "loop-metrics.jsonl").write_text(row + "\n", encoding="utf-8")


def test_non_scorable_only_turn_is_not_counted_as_checklist_miss(tmp_path: Path) -> None:
    """A turn that edits only a markdown file must not raise checklist_skipped
    or edits_without_validation -- those obligations are conditional on
    touching a scorable source file."""
    _write_loop_metrics(
        tmp_path,
        '{"ts":1,"files_edited":["README.md"],"gate_skipped_files":[],'
        '"lookup_docs_called":false,"checklist_called":false,"tools_used":[]}',
    )

    report = compute_gaps(tmp_path, called_tools={"tapps_session_start"})

    assert "checklist_skipped" not in report["gaps"]
    assert "edits_without_validation" not in report["gaps"]


def test_negative_control_library_use_without_lookup_still_flagged(tmp_path: Path) -> None:
    """A turn that DOES edit a scorable file and use an external library
    without calling tapps_lookup_docs must still be flagged -- the
    conditional-gating fix must not accidentally suppress a real miss."""
    src = tmp_path / "mod.py"
    src.write_text("import reportlab\n", encoding="utf-8")
    _write_loop_metrics(
        tmp_path,
        '{"ts":1,"files_edited":["mod.py"],"gate_skipped_files":[],'
        '"lookup_docs_called":false,"checklist_called":true,"tools_used":[]}',
    )

    report = compute_gaps(tmp_path, called_tools={"tapps_session_start", "tapps_checklist"})

    assert "library_uses_without_lookup_docs" in report["gaps"]
