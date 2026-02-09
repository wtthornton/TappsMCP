"""Radon complexity / maintainability wrapper."""

from __future__ import annotations

import json

import structlog

from tapps_mcp.scoring.constants import COMPLEXITY_SCALING_FACTOR, clamp_individual
from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

logger = structlog.get_logger(__name__)


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

    Lower complexity → higher score (inverted by the overall scorer).
    This returns the *raw* complexity score (higher = more complex).
    """
    if not entries:
        return 1.0  # trivial code
    max_cc = max(float(str(e.get("complexity", 0))) for e in entries)
    return clamp_individual(max_cc / COMPLEXITY_SCALING_FACTOR)


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
    """Run ``radon cc -j`` on a single file asynchronously."""
    result = await run_command_async(["radon", "cc", "-j", file_path], cwd=cwd, timeout=timeout)
    if result.timed_out or not result.stdout.strip():
        return []
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
    """Async variant of ``run_radon_mi``."""
    result = await run_command_async(["radon", "mi", "-j", file_path], cwd=cwd, timeout=timeout)
    if result.timed_out or not result.stdout.strip():
        return 50.0
    mi_map = parse_radon_mi_json(result.stdout)
    if not mi_map:
        return 50.0
    return next(iter(mi_map.values()), 50.0)
