"""Helpers for the ``tapps_session_start`` tool handler.

Extracted from ``server_pipeline_tools.py`` to keep that module a thin
orchestrator. Covers data-assembly, path-mapping detection, checklist
session id lookup, structured-output attachment, and phase collection.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

from tapps_mcp.server_helpers import (
    collect_session_hive_status,
    initial_session_hive_status,
)

_logger = structlog.get_logger(__name__)

# TAP-1414: Python projects with ruff/mypy missing run the quality gate degraded
# (ruff and mypy are the two highest-signal Python checkers). Surface a loud
# warning at session start instead of letting agents discover this by reading
# tool-versions.json after they've already shipped degraded results.
_PYTHON_CRITICAL_CHECKERS: tuple[str, ...] = ("ruff", "mypy")
_PYTHON_DEGRADED_WARNING = (
    "WARNING: ruff and mypy are missing — quality gate will run degraded. "
    "Install: uv tool install tapps-mcp --with ruff --with mypy"
)
_PYTHON_DEGRADED_WARNING_SINGLE = (
    "WARNING: {checker} is missing — quality gate will run degraded. "
    "Install: uv tool install tapps-mcp --with {checker}"
)


def _is_python_project(project_root: Path) -> bool:
    """Return True if the project root looks like a Python project."""
    if (project_root / "pyproject.toml").exists():
        return True
    if (project_root / "setup.py").exists() or (project_root / "setup.cfg").exists():
        return True
    try:
        return any(project_root.glob("*.py"))
    except OSError:
        return False


def compute_python_degraded_checkers(
    project_root: Path,
    installed_checkers: list[Any],
) -> tuple[list[str], str | None]:
    """Return (degraded_checker_names, warning_message) for a Python project.

    Returns ``([], None)`` when the project is not Python or all critical
    checkers are available. Each entry of ``installed_checkers`` may be a dict
    or an object with ``name``/``available`` attributes.
    """
    if not _is_python_project(project_root):
        return [], None

    degraded: list[str] = []
    for entry in installed_checkers:
        if isinstance(entry, dict):
            name = entry.get("name", "")
            available = bool(entry.get("available", False))
        else:
            name = getattr(entry, "name", "")
            available = bool(getattr(entry, "available", False))
        if name in _PYTHON_CRITICAL_CHECKERS and not available:
            degraded.append(name)

    if not degraded:
        return [], None

    if len(degraded) == 1:
        warning = _PYTHON_DEGRADED_WARNING_SINGLE.format(checker=degraded[0])
    else:
        warning = _PYTHON_DEGRADED_WARNING
    return degraded, warning


def build_session_start_data(
    settings: Any,
    info: dict[str, Any],
    memory_status: dict[str, Any],
    hive_status: dict[str, Any],
    brain_bridge_health: dict[str, Any],
    checklist_sid: str | None,
    path_mapping: dict[str, Any] | None,
    timings: dict[str, int],
    docs_provider: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the main data dict for a full session_start response."""
    import shutil
    import sys

    server_info = dict(info["data"]["server"])
    server_info["executable"] = sys.executable
    server_info["binary_path"] = shutil.which("tapps-mcp") or ""

    data: dict[str, Any] = {
        "project_root": str(settings.project_root),
        "server": server_info,
        "configuration": info["data"]["configuration"],
        "installed_checkers": info["data"]["installed_checkers"],
        "checker_environment": info["data"].get("checker_environment", "mcp_server"),
        "checker_environment_note": info["data"].get(
            "checker_environment_note",
            "Checker availability reflects the MCP server process environment. "
            "Target project may have different tools installed.",
        ),
        "docs_provider": info["data"].get("docs_provider", docs_provider),
        "diagnostics": info["data"]["diagnostics"],
        "quick_start": info["data"].get("quick_start", []),
        "critical_rules": info["data"].get("critical_rules", []),
        "pipeline": info["data"]["pipeline"],
        "checklist_session_id": checklist_sid,
        "memory_status": memory_status,
        "hive_status": hive_status,
        "brain_bridge_health": brain_bridge_health,
        "memory_gc": "background",
        "memory_consolidation": "background",
        "memory_doc_validation": "background",
        "session_capture": "background",
        "timings": timings,
        "path_mapping": path_mapping,
        "cache": info["data"].get("cache"),
    }
    return data


def detect_path_mapping() -> tuple[dict[str, Any] | None, str | None]:
    """Detect Docker path mapping and optional container warning."""
    try:
        from tapps_core.common.utils import get_path_mapping, is_running_in_container

        if is_running_in_container():
            path_mapping = get_path_mapping()
            if path_mapping and not path_mapping.get("mapping_available"):
                warning = (
                    "Running in container but TAPPS_HOST_ROOT not set. "
                    "File paths will use container paths (e.g. /workspace/...). "
                    "Set TAPPS_HOST_ROOT to enable host path mapping."
                )
                return path_mapping, warning
            return path_mapping, None
    except Exception:
        _logger.debug("path_mapping_detection_failed", exc_info=True)
    return None, None


def get_checklist_session_id() -> str | None:
    """Return the active checklist session id (or None if unavailable)."""
    try:
        from tapps_mcp.tools.checklist import CallTracker

        return CallTracker.get_active_checklist_session_id()
    except ImportError:
        return None


def attach_session_start_structured_output(
    resp: dict[str, Any],
    info: dict[str, Any],
) -> None:
    """Attach structured SessionStartOutput content to the response dict."""
    try:
        from tapps_mcp.common.output_schemas import SessionStartOutput
        from tapps_mcp.project.profiler import detect_project_signals

        checker_names = [
            c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "")
            for c in info["data"].get("installed_checkers", [])
        ]
        _proj_root = Path(info["data"]["configuration"].get("project_root", "."))
        _has_ci, _has_docker, _has_tests = detect_project_signals(_proj_root)
        structured = SessionStartOutput(
            server_version=info["data"]["server"].get("version", ""),
            project_root=str(_proj_root),
            project_type=None,
            quality_preset=info["data"]["configuration"].get("quality_preset", "standard"),
            installed_checkers=[n for n in checker_names if n],
            has_ci=_has_ci,
            has_docker=_has_docker,
            has_tests=_has_tests,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        _logger.debug("structured_output_failed: tapps_session_start", exc_info=True)


def attach_quick_session_structured_output(
    resp: dict[str, Any],
    settings: Any,
    installed: list[Any],
) -> None:
    """Attach SessionStartOutput for the quick path."""
    try:
        from tapps_mcp import __version__
        from tapps_mcp.common.output_schemas import SessionStartOutput
        from tapps_mcp.project.profiler import detect_project_signals

        checker_names = [t.name for t in installed if t.available]
        _has_ci, _has_docker, _has_tests = detect_project_signals(settings.project_root)
        structured = SessionStartOutput(
            server_version=__version__,
            project_root=str(settings.project_root),
            project_type=None,
            quality_preset=settings.quality_preset,
            installed_checkers=checker_names,
            has_ci=_has_ci,
            has_docker=_has_docker,
            has_tests=_has_tests,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        _logger.debug("structured_output_failed: tapps_session_start_quick", exc_info=True)


async def collect_session_start_phases(
    settings: Any,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, int]]:
    """Run the four timed phases that make up a full session_start.

    Returns (server_info, memory_status, hive_status, brain_bridge_health, timings).
    """
    from tapps_mcp.server import _server_info_async
    from tapps_mcp.tools.session_start_helpers import (
        _collect_brain_bridge_health,
        _collect_memory_status,
    )

    timings: dict[str, int] = {}

    phase_start = time.perf_counter_ns()
    info = await _server_info_async()
    timings["server_info_ms"] = (time.perf_counter_ns() - phase_start) // 1_000_000

    phase_start = time.perf_counter_ns()
    memory_status = _collect_memory_status(settings)
    timings["memory_status_ms"] = (time.perf_counter_ns() - phase_start) // 1_000_000

    phase_start = time.perf_counter_ns()
    hive_status: dict[str, Any] = initial_session_hive_status()
    try:
        hive_status = await collect_session_hive_status(settings)
    except Exception:
        _logger.debug("hive_status_check_failed", exc_info=True)
    timings["hive_status_ms"] = (time.perf_counter_ns() - phase_start) // 1_000_000

    phase_start = time.perf_counter_ns()
    brain_bridge_health = _collect_brain_bridge_health()
    timings["brain_bridge_health_ms"] = (time.perf_counter_ns() - phase_start) // 1_000_000

    return info, memory_status, hive_status, brain_bridge_health, timings


__all__ = [
    "attach_quick_session_structured_output",
    "attach_session_start_structured_output",
    "build_session_start_data",
    "collect_session_start_phases",
    "compute_python_degraded_checkers",
    "detect_path_mapping",
    "get_checklist_session_id",
]
