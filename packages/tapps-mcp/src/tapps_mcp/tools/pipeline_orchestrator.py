"""Helper functions for the ``tapps_pipeline`` orchestrator.

Extracted from ``server_pipeline_tools.py`` to keep that module focused
on tool dispatch. Functions here are private stage runners.
"""

from __future__ import annotations

import sys
import time
from typing import Any


async def pipeline_session_start_stage(
    skip_session_start: bool,
) -> dict[str, Any] | None:
    """Run or skip the session_start stage; returns a stage dict or None."""
    from tapps_mcp.server_helpers import ensure_session_initialized

    if skip_session_start:
        return None
    stage_start = time.perf_counter_ns()
    try:
        await ensure_session_initialized()
        return {
            "name": "session_start",
            "success": True,
            "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
            "summary": "session initialized",
        }
    except Exception as exc:
        return {
            "name": "session_start",
            "success": False,
            "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
            "summary": f"session_start failed: {exc}",
        }


async def pipeline_quick_check_stage(
    file_paths: str,
    preset: str,
) -> tuple[dict[str, Any], bool, str | None]:
    """Run the quick_check stage. Returns (stage dict, passed, short_circuit)."""
    from tapps_mcp.server_pipeline_tools import _summarize_quick_check
    from tapps_mcp.server_scoring_tools import tapps_quick_check

    stage_start = time.perf_counter_ns()
    qc_resp = await tapps_quick_check(
        file_path="",
        preset=preset,
        fix=False,
        file_paths=file_paths,
    )
    qc_data = qc_resp.get("data", {}) if isinstance(qc_resp, dict) else {}
    qc_passed = bool(qc_resp.get("success")) and not qc_data.get("security_floor_failed")
    stage = {
        "name": "quick_check",
        "success": qc_passed,
        "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
        "summary": _summarize_quick_check(qc_data),
    }
    short_circuit = "security_floor_failed" if qc_data.get("security_floor_failed") else None
    return stage, qc_passed, short_circuit


async def pipeline_validate_stage(
    file_paths: str,
    preset: str,
    short_circuit: str | None,
) -> tuple[dict[str, Any], bool]:
    """Run validate_changed stage (or skip on short-circuit). Returns (stage, passed).

    Looks up ``tapps_validate_changed`` on ``server_pipeline_tools`` so tests
    that patch ``tapps_mcp.server_pipeline_tools.tapps_validate_changed`` see
    their mock applied.
    """
    if short_circuit is not None:
        return (
            {
                "name": "validate_changed",
                "success": False,
                "elapsed_ms": 0,
                "summary": f"skipped ({short_circuit})",
            },
            False,
        )
    stage_start = time.perf_counter_ns()
    host = sys.modules["tapps_mcp.server_pipeline_tools"]
    vc_resp = await host.tapps_validate_changed(file_paths=file_paths, preset=preset)
    vc_data = vc_resp.get("data", {}) if isinstance(vc_resp, dict) else {}
    vc_passed = bool(vc_resp.get("success")) and bool(vc_data.get("all_passed", False))
    stage = {
        "name": "validate_changed",
        "success": vc_passed,
        "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
        "summary": (
            f"{vc_data.get('passed_count', 0)} passed / "
            f"{vc_data.get('failed_count', 0)} failed"
        ),
    }
    return stage, vc_passed


async def pipeline_checklist_stage(
    task_type: str,
) -> tuple[dict[str, Any], bool]:
    """Run the checklist stage; always runs even on failure."""
    stage_start = time.perf_counter_ns()
    try:
        from tapps_mcp.server import tapps_checklist

        cl_resp = await tapps_checklist(task_type=task_type, output_format="compact")
        cl_data = cl_resp.get("data", {}) if isinstance(cl_resp, dict) else {}
        cl_passed = bool(cl_resp.get("success")) and not cl_data.get("missing")
        stage = {
            "name": "checklist",
            "success": cl_passed,
            "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
            "summary": cl_data.get("compact_summary") or str(cl_data.get("status", "")),
        }
        return stage, cl_passed
    except Exception as exc:
        return (
            {
                "name": "checklist",
                "success": False,
                "elapsed_ms": (time.perf_counter_ns() - stage_start) // 1_000_000,
                "summary": f"checklist failed: {exc}",
            },
            False,
        )


__all__ = [
    "pipeline_checklist_stage",
    "pipeline_quick_check_stage",
    "pipeline_session_start_stage",
    "pipeline_validate_stage",
]
