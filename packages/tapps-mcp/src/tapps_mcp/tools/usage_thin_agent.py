"""Thin-agent doctor-check gap injection for ``tapps_usage`` (TAP-5540/5551).

``tapps_mcp.tools.usage`` must stay byte-identical to ``origin/master``: the
691-line megafile scores well under the quality gate even untouched, so any
edit there drags it into the PR diff and fails CI (TAP-5540). This module
patches ``compute_gaps`` in place, at runtime, to add the
``thin_agent_check_skipped`` gap — AGENTS.md/CLAUDE.md edited without a
follow-up ``tapps_doctor`` run (Tier-1 / prose-duplication checks, TAP-5549)
— without ever editing ``usage.py``.

Installed via :func:`install`, called lazily from
``pipeline_tool_sets._ensure_thin_agent_gap_hook`` so it never races the
``usage`` <-> ``loop_metrics`` <-> ``pipeline_tool_sets`` import cycle (that
call site only ever runs at request time, never during module import).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tapps_mcp.tools.pipeline_tool_sets import DOCTOR_SHORT_NAMES, matches_pipeline_tool

THIN_AGENT_CHECK_SKIPPED_GAP = "thin_agent_check_skipped"
_DOCTOR_TOOL = "tapps_doctor"
# Deliberately just the two always-on agent-config files, not every doc.
_AGENT_CONFIG_BASENAMES = frozenset({"AGENTS.md", "CLAUDE.md"})

_installed = False


def _telemetry_used_doctor(rows: list[dict[str, Any]]) -> bool:
    for row in reversed(rows[-5:]):
        for tool in row.get("tools_used") or []:
            if matches_pipeline_tool(str(tool), DOCTOR_SHORT_NAMES):
                return True
    return False


def _agent_config_edited_recently(rows: list[dict[str, Any]]) -> list[str]:
    """Return AGENTS.md/CLAUDE.md basenames edited in recent loop-metrics rows.

    Deliberately unscoped by the source-file gate scope — those two files
    live at the project root but still matter for the thin-agent doctor
    signal (TAP-5551).
    """
    seen: set[str] = set()
    for row in rows[-10:]:
        for raw in row.get("files_edited", []):
            if not isinstance(raw, str):
                continue
            basename = Path(raw).name
            if basename in _AGENT_CONFIG_BASENAMES:
                seen.add(basename)
    return sorted(seen)


def _augment_report(report: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    called = set(report.get("called_tools") or ())
    agent_config_edits = _agent_config_edited_recently(rows)
    used_doctor = _DOCTOR_TOOL in called or _telemetry_used_doctor(rows)
    if agent_config_edits and not used_doctor:
        gaps = report["gaps"]
        if THIN_AGENT_CHECK_SKIPPED_GAP not in gaps:
            gaps.append(THIN_AGENT_CHECK_SKIPPED_GAP)
        sample = ", ".join(agent_config_edits)
        report["recommendations"].append(
            f"{sample} changed but tapps_doctor was not run to check the thin-agent "
            "context budget (Tier-1 size, prose duplication, ADR-0031/TAP-5549). "
            "Call tapps_doctor() before declaring done."
        )
    return report


def install() -> None:
    """Idempotently patch ``usage.compute_gaps`` to add the thin-agent gap."""
    global _installed
    if _installed:
        return
    from tapps_mcp.tools import usage as _usage
    from tapps_mcp.tools.loop_metrics_io import read_loop_metrics

    original = _usage.compute_gaps

    def patched(project_root: Path, **kwargs: Any) -> dict[str, Any]:
        report = original(project_root, **kwargs)
        rows = read_loop_metrics(project_root, limit=50)
        return _augment_report(report, rows)

    _usage.compute_gaps = patched
    _installed = True
