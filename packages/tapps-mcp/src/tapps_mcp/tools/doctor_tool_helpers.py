"""Helper functions for ``tapps_doctor`` (TAP-6881).

Each of ``tapps_doctor``'s best-effort enrichment blocks (loop metrics,
degraded-checker detection, push-test log, completion-gate hook presence,
usage gaps) is its own small function here instead of one large inline
function body -- extracted to keep both this module and
``tools/admin_tools.py`` (which calls these) within the maintainability
gate. Every function is best-effort: on any internal failure it returns
``None`` (or an empty/degraded shape) rather than raising, matching the
original inline ``try/except: pass`` behavior in ``tapps_doctor``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def doctor_loop_metrics(root: Path) -> dict[str, Any]:
    """TAP-1333: 7-day MCP-call ratio + gate-skip rate, or a degraded stub."""
    try:
        from tapps_mcp.tools.loop_metrics import compute_rolling_stats

        return compute_rolling_stats(root)
    except Exception:
        return {"loops": 0, "error": "loop_metrics_unavailable"}


def doctor_degraded_checkers(root: Path) -> tuple[list[str], str] | None:
    """TAP-1414: ruff/mypy-missing summary for parity with tapps_session_start."""
    try:
        from tapps_mcp.tools.session_start_core import compute_python_degraded_checkers
        from tapps_mcp.tools.tool_detection import detect_installed_tools

        degraded_checkers, degraded_warning = compute_python_degraded_checkers(
            root, detect_installed_tools()
        )
        if degraded_checkers:
            return degraded_checkers, degraded_warning
    except Exception:
        pass
    return None


def doctor_push_test_log(root: Path) -> dict[str, Any] | None:
    """TAP-2453: last 5 background push-test results, or None if no log."""
    try:
        import json as _json

        push_log = root / ".tapps-mcp" / ".push-test-log"
        if not push_log.exists():
            return None
        raw_lines = push_log.read_text(encoding="utf-8").splitlines()
        entries: list[dict[str, object]] = []
        for raw_line in raw_lines[-5:]:
            stripped = raw_line.strip()
            if stripped:
                try:
                    entries.append(_json.loads(stripped))
                except _json.JSONDecodeError:
                    entries.append({"raw": stripped})
        last_status = entries[-1].get("status", "UNKNOWN") if entries else "NO_RESULTS"
        block: dict[str, Any] = {
            "last_5_entries": entries,
            "last_status": last_status,
            "log_path": str(push_log),
        }
        if last_status == "FAIL":
            block["warning"] = (
                "Background full-suite test run FAILED after last push. "
                f"Inspect {push_log} or .tapps-mcp/.bg-test-stdout.log."
            )
        return block
    except Exception:
        return None


def doctor_completion_gate_hook(root: Path, load_settings: Any) -> dict[str, Any] | None:
    """Completion-gate Stop-hook presence (warn-mode telemetry path).

    When missing, the agent gets no "edits without validation" warn at
    end-of-turn. ``load_settings`` is passed in (rather than imported here)
    so the caller controls which ``load_settings`` reference is used --
    keeps this helper agnostic to the late-binding patch-target concerns
    that apply to its caller.
    """
    try:
        claude_hook = root / ".claude" / "hooks" / "tapps-stop.sh"
        cursor_hook = root / ".cursor" / "hooks" / "tapps-stop.sh"
        hook_paths = [p for p in (claude_hook, cursor_hook) if p.exists()]
        installed = bool(hook_paths)
        gate_settings = load_settings(root)
        gate_mode = gate_settings.cursor_stop_completion_gate_resolved()
        block: dict[str, Any] = {
            "paths": [str(p) for p in hook_paths],
            "installed": installed,
            "mode": gate_mode,
            "configured": gate_settings.cursor_stop_completion_gate,
        }
        warnings: list[str] = []
        if not installed:
            warnings.append(
                "Stop hook tapps-stop.sh is not installed (.claude or .cursor). "
                "Completion-gate warn-mode telemetry is inactive. Run tapps_upgrade."
            )
        if gate_mode == "block":
            warnings.append(
                "cursor_stop_completion_gate resolves to block — run tapps-mcp upgrade "
                "to pin warn and avoid BLOCKED followup messages."
            )
        elif gate_settings.cursor_stop_completion_gate is None:
            warnings.append(
                "cursor_stop_completion_gate not pinned in .tapps-mcp.yaml — "
                "run tapps-mcp upgrade to add cursor_stop_completion_gate: warn."
            )
        if warnings:
            block["warning"] = " ".join(warnings)
        return block
    except Exception:
        return None


def doctor_usage_gaps(root: Path) -> dict[str, Any] | None:
    """Per-session usage gap summary (edits-without-validation, etc.)."""
    try:
        from tapps_mcp.tools.usage import compute_gaps

        usage_summary = compute_gaps(root)
        gaps = usage_summary.get("gaps", [])
        recs = usage_summary.get("recommendations", [])
        return {
            "gap_count": len(gaps),
            "gaps": gaps,
            "top_recommendation": recs[0] if recs else None,
        }
    except Exception:
        return None


__all__ = [
    "doctor_completion_gate_hook",
    "doctor_degraded_checkers",
    "doctor_loop_metrics",
    "doctor_push_test_log",
    "doctor_usage_gaps",
]
