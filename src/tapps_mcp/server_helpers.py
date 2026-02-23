"""Helper functions extracted from server.py to reduce complexity and duplication."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tapps_mcp.scoring.scorer import CodeScorer as _CodeScorerType

# ---------------------------------------------------------------------------
# CodeScorer singleton — avoids re-instantiating on every tool call.
# ---------------------------------------------------------------------------

_scorer: _CodeScorerType | None = None


def _get_scorer() -> _CodeScorerType:
    """Return a lazily-initialized :class:`CodeScorer` singleton."""
    global _scorer  # noqa: PLW0603
    if _scorer is None:
        from tapps_mcp.scoring.scorer import CodeScorer

        _scorer = CodeScorer()
    return _scorer


def _reset_scorer_cache() -> None:
    """Reset the cached :class:`CodeScorer` singleton (for testing)."""
    global _scorer  # noqa: PLW0603
    _scorer = None


def error_response(tool_name: str, code: str, message: str) -> dict[str, Any]:
    """Build a standard error response envelope."""
    return {
        "tool": tool_name,
        "success": False,
        "elapsed_ms": 0,
        "error": {"code": code, "message": message},
    }


_SENTINEL = object()


def success_response(
    tool_name: str,
    elapsed_ms: int,
    data: dict[str, Any],
    *,
    degraded: bool | object = _SENTINEL,
    next_steps: list[str] | None = None,
    pipeline_progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard success response envelope.

    When *degraded* is explicitly passed (even as False), the key is included
    in the response.  When omitted, the key is absent.

    When *next_steps* is non-empty, it is included in ``data`` so the LLM
    sees actionable guidance.  Same for *pipeline_progress*.
    """
    if next_steps:
        data["next_steps"] = next_steps
    if pipeline_progress:
        data["pipeline_progress"] = pipeline_progress

    result: dict[str, Any] = {
        "tool": tool_name,
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": data,
    }
    if degraded is not _SENTINEL:
        result["degraded"] = degraded
    return result


def serialize_issues(
    issues: list[Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Serialize a list of Pydantic model issues, truncated to *limit*."""
    return [i.model_dump() for i in issues[:limit]]
