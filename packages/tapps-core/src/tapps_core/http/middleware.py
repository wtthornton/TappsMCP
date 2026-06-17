"""ASGI middleware for HTTP MCP fleet project-root routing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from tapps_core.http.request_context import (
    PROJECT_ROOT_HEADER,
    reset_request_project_root,
    set_request_project_root,
)

Send = Callable[[dict[str, Any]], Awaitable[None]]
Receive = Callable[[], Awaitable[dict[str, Any]]]
ASGIApp = Callable[[dict[str, Any], Receive, Send], Awaitable[None]]


class TappsProjectRootMiddleware:
    """Map ``X-Tapps-Project-Root`` to a contextvar for tool handlers."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        header_value = _header_value(scope, PROJECT_ROOT_HEADER)
        token = None
        if header_value:
            try:
                token = set_request_project_root(Path(header_value))
            except OSError:
                pass

        try:
            await self.app(scope, receive, send)
        finally:
            if token is not None:
                reset_request_project_root(token)


def _header_value(scope: dict[str, Any], name: str) -> str | None:
    target = name.lower().encode("ascii")
    for raw_key, raw_value in scope.get("headers", ()):
        if raw_key.lower() == target:
            return raw_value.decode("utf-8", errors="replace").strip() or None
    return None


def wrap_streamable_http_app(app: ASGIApp) -> ASGIApp:
    """Wrap a Streamable HTTP ASGI app with project-root middleware."""
    return TappsProjectRootMiddleware(app)
