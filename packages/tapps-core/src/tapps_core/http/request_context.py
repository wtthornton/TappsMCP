"""Per-request project root for shared HTTP MCP fleet (ADR-0024)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from pathlib import Path
from typing import Final, Literal

PROJECT_ROOT_HEADER = "X-Tapps-Project-Root"

#: Root handed to settings when a fleet request carries no project root at all
#: (TAP-6062 workspace-free mode). It is deliberately an empty, fleet-owned
#: directory: a workspace-free caller gets a valid, inert root instead of the
#: fleet process's own CWD, which would be somebody else's tree.
WORKSPACE_FREE_ROOT: Final[Path] = Path.home() / ".tapps-mcp" / "workspace-free"

WorkspaceMode = Literal["stdio", "scoped", "workspace-free"]

_request_project_root: ContextVar[Path | None] = ContextVar(
    "tapps_request_project_root",
    default=None,
)

# Distinct from "no project root": this says an HTTP request is in flight at
# all. Header-absent ``None`` cannot carry that, and the difference is
# load-bearing -- ``Path.cwd()`` is a correct default for a stdio server the
# host launched inside the repo, and a wrong-tree answer for a shared fleet
# process serving somebody else's request.
_in_http_request: ContextVar[bool] = ContextVar(
    "tapps_in_http_request",
    default=False,
)

# Scope granted by the fleet bearer token for the current request
# (``operator`` / ``runtime``); ``None`` outside an authenticated HTTP request.
_request_auth_scope: ContextVar[str | None] = ContextVar(
    "tapps_request_auth_scope",
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


def is_http_request() -> bool:
    """True while an HTTP fleet request is being served in this context."""
    return _in_http_request.get()


def mark_http_request() -> Token[bool]:
    """Flag the current context as serving an HTTP fleet request."""
    return _in_http_request.set(True)


def reset_http_request(token: Token[bool]) -> None:
    """Undo :func:`mark_http_request`."""
    _in_http_request.reset(token)


def get_request_auth_scope() -> str | None:
    """Return the fleet auth scope bound to the current request, if any."""
    return _request_auth_scope.get()


def set_request_auth_scope(scope: str | None) -> Token[str | None]:
    """Bind the fleet auth *scope* for the current async/task context."""
    return _request_auth_scope.set(scope)


def reset_request_auth_scope(token: Token[str | None]) -> None:
    """Restore the previous auth scope binding."""
    _request_auth_scope.reset(token)


def workspace_mode() -> WorkspaceMode:
    """Classify how the current request should resolve a project root.

    ``stdio``
        Not an HTTP request -- the process CWD is the workspace, unchanged.
    ``scoped``
        HTTP request carrying ``X-Tapps-Project-Root``.
    ``workspace-free``
        HTTP request with no project root. Tools that only need the network
        (docs, research) still work; tools that scan a tree must refuse
        rather than scan the fleet process's own directory.
    """
    if not is_http_request():
        return "stdio"
    if get_request_project_root() is not None:
        return "scoped"
    return "workspace-free"


def http_request_root_override(project_root: Path | None) -> tuple[Path | None, bool]:
    """Resolve a fleet request's root override and whether it may be cached.

    Returns ``(root, cacheable)``. ``root`` is the explicit argument, the
    header root, the workspace-free sentinel, or ``None`` meaning "fall back
    to env/CWD as a stdio server would". ``cacheable`` is False for anything
    request-scoped, so a per-request resolution never lands in a process
    singleton that later stdio callers read.
    """
    if project_root is not None:
        return project_root, False
    request_root = get_request_project_root()
    if request_root is not None:
        return request_root, False
    if is_http_request():
        return WORKSPACE_FREE_ROOT, False
    return None, True
