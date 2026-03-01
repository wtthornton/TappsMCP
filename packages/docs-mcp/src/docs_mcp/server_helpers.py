"""Helper functions for DocsMCP server — response builders and singleton caches."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docs_mcp.config.settings import DocsMCPSettings


# ---------------------------------------------------------------------------
# Settings singleton — avoids re-loading on every tool call.
# ---------------------------------------------------------------------------

_settings: DocsMCPSettings | None = None


def _get_settings() -> DocsMCPSettings:
    """Return a lazily-initialized :class:`DocsMCPSettings` singleton."""
    global _settings  # noqa: PLW0603
    if _settings is None:
        from docs_mcp.config.settings import load_docs_settings

        _settings = load_docs_settings()
    return _settings


def _reset_settings_cache() -> None:
    """Reset the cached :class:`DocsMCPSettings` singleton (for testing)."""
    global _settings  # noqa: PLW0603
    _settings = None


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


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
) -> dict[str, Any]:
    """Build a standard success response envelope.

    When *degraded* is explicitly passed (even as False), the key is included
    in the response.  When omitted, the key is absent.

    When *next_steps* is non-empty, it is included in ``data`` so the LLM
    sees actionable guidance.
    """
    if next_steps:
        data["next_steps"] = next_steps

    result: dict[str, Any] = {
        "tool": tool_name,
        "success": True,
        "elapsed_ms": elapsed_ms,
        "data": data,
    }
    if degraded is not _SENTINEL:
        result["degraded"] = degraded
    return result
