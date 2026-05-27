"""Procedural-tier memory writes for repeating tapps workflow patterns (TAP-2007).

Three sources are wired:
  1. ``tapps_quality_gate`` FAIL→PASS transitions — fix recipe written when a
     file that previously failed the gate now passes.
  2. ``tapps_impact_analysis`` completion — refactor sequence captured with
     severity + dependent counts + recommendations.
  3. ``docs_lint_linear_issue`` (docs-mcp) — PR-shape pattern written once per
     session; see ``docs_mcp.server_linear_tools``.

All writes are best-effort fire-and-forget — a brain outage must never block
the calling tool. Writes route through :func:`tapps_mcp.server_helpers._get_brain_bridge`
using ``tier="procedural"`` (30-day decay per brain tier definitions).
"""

from __future__ import annotations

import asyncio
import re
import threading
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Session-level gate-fail state
# ---------------------------------------------------------------------------

_gate_fail_lock = threading.Lock()
# resolved_file_path (str) → frozenset of failing category names from prior calls
_gate_fail_state: dict[str, set[str]] = {}


def _reset_gate_fail_state() -> None:
    """Clear recurrence state (for tests and process hygiene)."""
    with _gate_fail_lock:
        _gate_fail_state.clear()


def record_gate_outcome(file_path: str, passed: bool, failing_categories: list[str]) -> set[str]:
    """Record a quality gate outcome and return the *previous* failure set.

    Thread-safe.  Returns the set of categories that were failing BEFORE this
    call so the caller can decide whether a PASS represents a FAIL→PASS
    transition.

    Args:
        file_path: Absolute resolved path of the file just evaluated.
        passed: True when the gate passed.
        failing_categories: Category names that failed (empty when ``passed``).

    Returns:
        The previous failure set for *file_path* (empty set if never recorded).
    """
    with _gate_fail_lock:
        prev: set[str] = set(_gate_fail_state.get(file_path, set()))
        if passed:
            _gate_fail_state.pop(file_path, None)
        else:
            _gate_fail_state[file_path] = set(failing_categories)
    return prev


# ---------------------------------------------------------------------------
# Key and value helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")
_MAX_KEY = 128
_MAX_VALUE = 1024  # keep procedural entries concise


def _slugify(text: str) -> str:
    """Lowercase and replace non-slug chars with hyphens, capped at 48 chars."""
    return _SLUG_RE.sub("-", text.lower()).strip("-")[:48] or "unknown"


def _build_key(*parts: str) -> str:
    """Join slug parts into a brain-compatible key (max 128 chars)."""
    return ".".join(_slugify(p) for p in parts)[:_MAX_KEY]


def _trunc(s: str, limit: int = _MAX_VALUE) -> str:
    return s[:limit]


# ---------------------------------------------------------------------------
# Shared async write helper (supersede-then-save pattern)
# ---------------------------------------------------------------------------


async def _write_procedural(key: str, value: str, tags: list[str]) -> None:
    """Write one procedural memory entry via the brain bridge.

    Tries ``bridge.supersede`` first (preserves the history chain when the
    key already exists from a prior session). Falls back to ``bridge.save``
    on ``not_found`` or if supersede is unsupported. Never raises.
    """
    try:
        from tapps_mcp.server_helpers import _get_brain_bridge

        bridge = _get_brain_bridge()
        if bridge is None:
            logger.debug("procedural_write_skipped_no_bridge", key=key)
            return

        # --- supersede path ---
        if hasattr(bridge, "supersede"):
            try:
                sup: dict[str, Any] | None = await bridge.supersede(key=key, new_value=value)
                if sup is not None and not (
                    isinstance(sup, dict) and sup.get("error") == "not_found"
                ):
                    logger.debug("procedural_supersede_ok", key=key)
                    return
            except Exception:
                pass  # fall through to save

        # --- save path (first write or supersede not found) ---
        await bridge.save(
            key=key,
            value=value,
            tier="procedural",
            source="agent",
            source_agent="tapps-mcp",
            scope="project",
            tags=tags,
            skip_consolidation=True,
        )
        logger.debug("procedural_save_ok", key=key)
    except Exception:
        logger.debug("procedural_write_failed", key=key, exc_info=True)


def _fire(coro: Any) -> None:
    """Schedule *coro* as a fire-and-forget asyncio task.  Never raises."""
    try:
        asyncio.create_task(coro)  # noqa: RUF006
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Public API: fix recipe on FAIL→PASS (quality gate)
# ---------------------------------------------------------------------------


def fire_fix_recipe_on_pass(
    file_path: str,
    fixed_categories: set[str],
    score: float | None = None,
) -> None:
    """Write a procedural fix-recipe memory when a file transitions FAIL→PASS.

    Called from ``tapps_quality_gate`` when the gate passes after one or more
    prior failures on the same file in this session.  Best-effort.

    Args:
        file_path: Absolute resolved path that just passed the gate.
        fixed_categories: Category names that were failing before the fix.
        score: Optional overall score after the successful gate run.
    """
    if not fixed_categories:
        return

    path_stem = Path(file_path).stem
    key = _build_key("procedural", "fix-recipe", path_stem)
    cats_str = ", ".join(sorted(fixed_categories))
    score_part = f" (score {score:.1f})" if score is not None else ""
    value = _trunc(
        f"Fix recipe for {path_stem}: resolved gate failure(s) on [{cats_str}]{score_part}. "
        f"Path: {file_path}"
    )
    tags = ["procedural", "fix-recipe", "auto-captured", "tapps-mcp"]
    _fire(_write_procedural(key, value, tags))
    logger.info(
        "procedural_fix_recipe_scheduled",
        file_path=file_path,
        fixed_categories=sorted(fixed_categories),
    )


# ---------------------------------------------------------------------------
# Public API: refactor sequence (impact analysis)
# ---------------------------------------------------------------------------


def fire_refactor_sequence(
    file_path: str,
    severity: str,
    direct_count: int,
    recommendations: list[str],
) -> None:
    """Write a procedural refactor-sequence memory after impact analysis.

    Called from ``tapps_impact_analysis`` on completion.  Best-effort.

    Args:
        file_path: The analysed file path (resolved absolute).
        severity: Impact severity verdict (low/medium/high/critical).
        direct_count: Number of direct dependents.
        recommendations: Top recommendations from the impact report.
    """
    path_stem = Path(file_path).stem
    key = _build_key("procedural", "refactor", path_stem)
    recs_str = "; ".join(recommendations[:3]) if recommendations else "none"
    value = _trunc(
        f"Refactor sequence for {path_stem}: severity={severity}, "
        f"direct_dependents={direct_count}, recommendations=[{recs_str}]. "
        f"Path: {file_path}"
    )
    tags = ["procedural", "refactor-sequence", "auto-captured", "tapps-mcp"]
    _fire(_write_procedural(key, value, tags))
    logger.info(
        "procedural_refactor_sequence_scheduled",
        file_path=file_path,
        severity=severity,
        direct_count=direct_count,
    )
