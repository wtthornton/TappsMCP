"""Per-request project root for shared HTTP MCP fleet (ADR-0024)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from pathlib import Path

PROJECT_ROOT_HEADER = "X-Tapps-Project-Root"

_request_project_root: ContextVar[Path | None] = ContextVar(
    "tapps_request_project_root",
    default=None,
)


def get_request_project_root() -> Path | None:
    """Return the project root bound to the current HTTP request, if any."""
    return _request_project_root.get()


def set_request_project_root(root: Path) -> Token[Path | None]:
    """Bind *root* for the current async/task context."""
    return _request_project_root.set(root.resolve())


def reset_request_project_root(token: Token[Path | None]) -> None:
    """Restore the previous project root binding."""
    _request_project_root.reset(token)
