"""Radon complexity / maintainability wrapper.

Supports subprocess and direct-library modes.  When the subprocess
returns empty output (common in MCP server async contexts), the
direct-library fallback produces accurate results in-process.
"""

from __future__ import annotations

import json

import structlog

from tapps_core.config.feature_flags import feature_flags as _ff
from tapps_mcp.scoring.constants import COMPLEXITY_SCALING_FACTOR, clamp_individual
from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

logger = structlog.get_logger(__name__)

_RADON_AVAILABLE: bool | None = None  # cached import probe


# ---------------------------------------------------------------------------
# Cyclomatic complexity
# ---------------------------------------------------------------------------


def parse_radon_cc_json(raw: str) -> list[dict[str, object]]:
    """Parse ``radon cc -j`` JSON output.

    Returns a list of function-level complexity entries.
    """
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    # data is ``{"path": [{...}, ...]}``
    entries: list[dict[str, object]] = []
    for _path, funcs in data.items():
        if isinstance(funcs, list):
            entries.extend(funcs)
    return entries


def calculate_complexity_score(entries: list[dict[str, object]]) -> float:
    """Convert radon cc entries into a 0-10 complexity score.

    Uses a blended formula: ``0.7 * max_cc + 0.3 * avg_cc`` so that
    one outlier function does not tank the entire file score.

    Lower complexity -> higher score (inverted by the overall scorer).
    This returns the *raw* complexity score (higher = more complex).
    """
    if not entries:
        return 1.0  # trivial code
    cc_values = [float(str(e.get("complexity", 0))) for e in entries]
    max_cc = max(cc_values)
    avg_cc = sum(cc_values) / len(cc_values)
    blended = _BLEND_MAX * max_cc + _BLEND_AVG * avg_cc
    return clamp_individual(blended / COMPLEXITY_SCALING_FACTOR)


# Blending weights for complexity scoring (Story 9.3)
_BLEND_MAX: float = 0.7
_BLEND_AVG: float = 0.3


def run_radon_cc(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[dict[str, object]]:
    """Run ``radon cc -j`` on a single file synchronously."""
    result = run_command(["radon", "cc", "-j", file_path], cwd=cwd, timeout=timeout)
    if result.timed_out or not result.stdout.strip():
        return []
    return parse_radon_cc_json(result.stdout)


async def run_radon_cc_async(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[dict[str, object]]:
    """Run ``radon cc -j`` on a single file asynchronously.

    Falls back to direct library import when the subprocess returns
    empty output (common in MCP async contexts).
    """
    result = await run_command_async(["radon", "cc", "-j", file_path], cwd=cwd, timeout=timeout)
    if result.timed_out:
        logger.warning("radon_cc_timeout", file=file_path, timeout=timeout)
        return _radon_cc_direct(file_path)
    if not result.stdout.strip():
        logger.info(
            "radon_cc_empty_subprocess",
            file=file_path,
            returncode=result.returncode,
            stderr=result.stderr[:200] if result.stderr else "",
        )
        return _radon_cc_direct(file_path)
    return parse_radon_cc_json(result.stdout)


# ---------------------------------------------------------------------------
# Maintainability index
# ---------------------------------------------------------------------------


def parse_radon_mi_json(raw: str) -> dict[str, float]:
    """Parse ``radon mi -j`` JSON output.

    Returns ``{path: mi_score}`` mapping.
    """
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    result: dict[str, float] = {}
    for path, val in data.items():
        if isinstance(val, dict):
            result[path] = float(val.get("mi", 50.0))
        elif isinstance(val, (int, float)):
            result[path] = float(val)
    return result


def calculate_maintainability_score(mi_value: float) -> float:
    """Convert radon MI value (0-100) to a 0-10 score."""
    return clamp_individual(mi_value / 10.0)


def run_radon_mi(file_path: str, *, cwd: str | None = None, timeout: int = 30) -> float:
    """Run ``radon mi -j`` and return the MI value for the file.

    Returns 50.0 (neutral) if radon is unavailable or fails.
    """
    result = run_command(["radon", "mi", "-j", file_path], cwd=cwd, timeout=timeout)
    if result.timed_out or not result.stdout.strip():
        return 50.0
    mi_map = parse_radon_mi_json(result.stdout)
    if not mi_map:
        return 50.0
    # Return the first (and typically only) value
    return next(iter(mi_map.values()), 50.0)


async def run_radon_mi_async(file_path: str, *, cwd: str | None = None, timeout: int = 30) -> float:
    """Async variant of ``run_radon_mi``.

    Falls back to direct library import when the subprocess returns
    empty output.
    """
    result = await run_command_async(["radon", "mi", "-j", file_path], cwd=cwd, timeout=timeout)
    if result.timed_out:
        logger.warning("radon_mi_timeout", file=file_path, timeout=timeout)
        return _radon_mi_direct(file_path)
    if not result.stdout.strip():
        logger.info(
            "radon_mi_empty_subprocess",
            file=file_path,
            returncode=result.returncode,
            stderr=result.stderr[:200] if result.stderr else "",
        )
        return _radon_mi_direct(file_path)
    mi_map = parse_radon_mi_json(result.stdout)
    if not mi_map:
        return _radon_mi_direct(file_path)
    return next(iter(mi_map.values()), 50.0)


# ---------------------------------------------------------------------------
# Direct library fallback (no subprocess)
# ---------------------------------------------------------------------------


def _is_radon_importable() -> bool:
    """Check whether the radon library is available for direct import.

    Delegates to :data:`tapps_core.config.feature_flags.feature_flags`.
    """
    global _RADON_AVAILABLE
    if _RADON_AVAILABLE is None:
        _RADON_AVAILABLE = _ff.radon
    return _RADON_AVAILABLE


def _radon_cc_direct(file_path: str) -> list[dict[str, object]]:
    """Compute cyclomatic complexity using radon as a library.

    Returns the same structure as ``parse_radon_cc_json`` output.
    """
    if not _is_radon_importable():
        logger.debug("radon_library_unavailable", purpose="cc")
        return []
    try:
        from radon.complexity import SCORE, cc_visit

        code = _read_source(file_path)
        if code is None:
            return []
        blocks = cc_visit(code)
        entries: list[dict[str, object]] = []
        for block in blocks:
            entries.append(
                {
                    "name": block.name,
                    "type": block.letter,
                    "complexity": block.complexity,
                    "lineno": block.lineno,
                    "endline": block.endline,
                    "rank": SCORE[block.complexity - 1] if block.complexity <= len(SCORE) else "F",
                }
            )
        logger.info("radon_cc_direct_success", file=file_path, functions=len(entries))
        return entries
    except Exception as exc:
        logger.warning("radon_cc_direct_failed", file=file_path, error=str(exc))
        return []


def _radon_mi_direct(file_path: str) -> float:
    """Compute maintainability index using radon as a library.

    Returns the MI value (0-100), or 50.0 on failure.
    """
    if not _is_radon_importable():
        logger.debug("radon_library_unavailable", purpose="mi")
        return 50.0
    try:
        from radon.metrics import mi_visit

        code = _read_source(file_path)
        if code is None:
            return 50.0
        mi_value: float = mi_visit(code, multi=True)
        logger.info("radon_mi_direct_success", file=file_path, mi=round(mi_value, 2))
        return mi_value
    except Exception as exc:
        logger.warning("radon_mi_direct_failed", file=file_path, error=str(exc))
        return 50.0


# ---------------------------------------------------------------------------
# Halstead metrics
# ---------------------------------------------------------------------------


def parse_radon_hal_json(raw: str) -> list[dict[str, object]]:
    """Parse ``radon hal -j`` JSON output.

    Returns a flat list of per-function Halstead report dicts with keys:
    ``name``, ``volume``, ``difficulty``, ``effort``, ``bugs``,
    ``vocabulary``, ``length``.
    """
    if not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    entries: list[dict[str, object]] = []
    for _path, content in data.items():
        if not isinstance(content, dict):
            continue
        # radon hal -j produces {"path": {"total": [...], "functions": [...]}}
        functions = content.get("functions", [])
        if isinstance(functions, list):
            for func in functions:
                if isinstance(func, (list, tuple)) and len(func) >= 2:
                    name, report = func[0], func[1]
                    entries.append(_hal_report_to_dict(str(name), report))
                elif isinstance(func, dict):
                    entries.append(_hal_report_to_dict(str(func.get("name", "")), func))
    return entries


def _hal_report_to_dict(name: str, report: object) -> dict[str, object]:
    """Convert a Halstead report (namedtuple or dict) to a flat dict."""
    if isinstance(report, dict):
        return {
            "name": name,
            "volume": float(report.get("volume", 0)),
            "difficulty": float(report.get("difficulty", 0)),
            "effort": float(report.get("effort", 0)),
            "bugs": float(report.get("bugs", 0)),
            "vocabulary": int(report.get("vocabulary", 0)),
            "length": int(report.get("length", 0)),
        }
    # namedtuple from radon.metrics.h_visit
    return {
        "name": name,
        "volume": float(getattr(report, "volume", 0)),
        "difficulty": float(getattr(report, "difficulty", 0)),
        "effort": float(getattr(report, "effort", 0)),
        "bugs": float(getattr(report, "bugs", 0)),
        "vocabulary": int(getattr(report, "vocabulary", 0)),
        "length": int(getattr(report, "length", 0)),
    }


def run_radon_hal(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[dict[str, object]]:
    """Run ``radon hal -j`` on a single file synchronously."""
    result = run_command(["radon", "hal", "-j", file_path], cwd=cwd, timeout=timeout)
    if result.timed_out or not result.stdout.strip():
        return []
    return parse_radon_hal_json(result.stdout)


async def run_radon_hal_async(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[dict[str, object]]:
    """Run ``radon hal -j`` on a single file asynchronously.

    Falls back to direct library import when the subprocess returns
    empty output (common in MCP async contexts).
    """
    result = await run_command_async(["radon", "hal", "-j", file_path], cwd=cwd, timeout=timeout)
    if result.timed_out:
        logger.warning("radon_hal_timeout", file=file_path, timeout=timeout)
        return _radon_hal_direct(file_path)
    if not result.stdout.strip():
        logger.info(
            "radon_hal_empty_subprocess",
            file=file_path,
            returncode=result.returncode,
            stderr=result.stderr[:200] if result.stderr else "",
        )
        return _radon_hal_direct(file_path)
    return parse_radon_hal_json(result.stdout)


def _radon_hal_direct(file_path: str) -> list[dict[str, object]]:
    """Compute Halstead metrics using radon as a library.

    Returns per-function Halstead report dicts.
    """
    if not _is_radon_importable():
        logger.debug("radon_library_unavailable", purpose="hal")
        return []
    try:
        from radon.metrics import h_visit

        code = _read_source(file_path)
        if code is None:
            return []
        hal_result = h_visit(code)
        # h_visit returns Halstead(total_report, [("func_name", report), ...])
        per_func = hal_result[1] if len(hal_result) > 1 else []
        entries: list[dict[str, object]] = []
        for func in per_func:
            if isinstance(func, (list, tuple)) and len(func) >= 2:
                entries.append(_hal_report_to_dict(str(func[0]), func[1]))
        logger.info("radon_hal_direct_success", file=file_path, functions=len(entries))
        return entries
    except Exception as exc:
        logger.warning("radon_hal_direct_failed", file=file_path, error=str(exc))
        return []


def _read_source(file_path: str) -> str | None:
    """Read a source file for direct radon analysis."""
    try:
        from pathlib import Path

        return Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("radon_read_failed", file=file_path, error=str(exc))
        return None
