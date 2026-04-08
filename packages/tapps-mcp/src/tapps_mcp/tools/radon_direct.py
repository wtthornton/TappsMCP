"""Direct radon library analysis - no subprocess required.

Uses ``radon.complexity.cc_visit``, ``radon.metrics.mi_visit``, and
``radon.metrics.h_visit`` for in-process cyclomatic complexity,
maintainability index, and Halstead metrics analysis.
This module is the primary path for ``mode="direct"`` scoring.
"""

from __future__ import annotations

import structlog

from tapps_core.config.feature_flags import feature_flags as _ff

logger = structlog.get_logger(__name__)

# Kept for backward compatibility with tests that patch _RADON_AVAILABLE.
_RADON_AVAILABLE: bool | None = None


def is_available() -> bool:
    """Check whether the radon library is importable.

    Delegates to :data:`tapps_core.config.feature_flags.feature_flags`.
    """
    global _RADON_AVAILABLE
    if _RADON_AVAILABLE is None:
        _RADON_AVAILABLE = _ff.radon
    return _RADON_AVAILABLE


def _read_source(file_path: str) -> str | None:
    """Read a source file for direct radon analysis."""
    try:
        from pathlib import Path

        return Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("radon_direct_read_failed", file=file_path, error=str(exc))
        return None


def cc_direct(file_path: str) -> list[dict[str, object]]:
    """Compute cyclomatic complexity using radon as a library.

    Returns the same structure as ``parse_radon_cc_json`` output so
    callers can use the result interchangeably.
    """
    if not is_available():
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


def mi_direct(file_path: str) -> float:
    """Compute maintainability index using radon as a library.

    Returns the MI value (0-100), or 50.0 on failure.
    """
    if not is_available():
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


def hal_direct(file_path: str) -> list[dict[str, object]]:
    """Compute Halstead metrics using radon as a library.

    Returns per-function Halstead report dicts matching the structure
    produced by :func:`tapps_mcp.tools.radon.parse_radon_hal_json`.
    """
    if not is_available():
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
                name, report = str(func[0]), func[1]
                entries.append(
                    {
                        "name": name,
                        "volume": float(getattr(report, "volume", 0)),
                        "difficulty": float(getattr(report, "difficulty", 0)),
                        "effort": float(getattr(report, "effort", 0)),
                        "bugs": float(getattr(report, "bugs", 0)),
                        "vocabulary": int(getattr(report, "vocabulary", 0)),
                        "length": int(getattr(report, "length", 0)),
                    }
                )
        logger.info("radon_hal_direct_success", file=file_path, functions=len(entries))
        return entries
    except Exception as exc:
        logger.warning("radon_hal_direct_failed", file=file_path, error=str(exc))
        return []
