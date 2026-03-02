"""Direct radon library analysis - no subprocess required.

Uses ``radon.complexity.cc_visit`` and ``radon.metrics.mi_visit`` for
in-process cyclomatic complexity and maintainability index analysis.
This module is the primary path for ``mode="direct"`` scoring.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

_RADON_AVAILABLE: bool | None = None


def is_available() -> bool:
    """Check whether the radon library is importable."""
    global _RADON_AVAILABLE
    if _RADON_AVAILABLE is None:
        import importlib.util

        try:
            _RADON_AVAILABLE = (
                importlib.util.find_spec("radon.complexity") is not None
                and importlib.util.find_spec("radon.metrics") is not None
            )
        except (ModuleNotFoundError, ValueError):
            _RADON_AVAILABLE = False
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
