"""ASGI middleware for HTTP MCP fleet project-root routing."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import structlog

from tapps_core.http.request_context import (
    PROJECT_ROOT_HEADER,
    reset_request_project_root,
    set_request_project_root,
)

logger = structlog.get_logger(__name__)

Send = Callable[[dict[str, Any]], Awaitable[None]]
Receive = Callable[[], Awaitable[dict[str, Any]]]
ASGIApp = Callable[[dict[str, Any], Receive, Send], Awaitable[None]]

# Substrings (lower-cased) that identify a request landing on the MCP SDK's
# StreamableHTTP session manager outside its lifespan window -- i.e. before
# ``run()`` started the task group or after shutdown tore it down. The SDK
# raises a bare ``RuntimeError`` here, which would otherwise surface as a 500
# and make MCP clients (Cursor) latch the server into a permanent "Error".
_SHUTDOWN_WINDOW_SIGNALS = ("task group is not initialized",)

_RETRY_AFTER_SECONDS = "1"


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
            with contextlib.suppress(OSError):
                token = set_request_project_root(Path(header_value))

        response_started = False

        async def _send(message: dict[str, Any]) -> None:
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except RuntimeError as exc:
            # Only convert the SDK shutdown-window race into a retryable 503,
            # and only when nothing has been sent yet. Genuine 500s and any
            # error after the response started must propagate unchanged.
            if response_started or not _is_shutdown_window_error(exc):
                raise
            logger.warning("http.shutdown_window_request", error=str(exc))
            await _send_retryable_503(send)
        finally:
            if token is not None:
                reset_request_project_root(token)


def _is_shutdown_window_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(signal in message for signal in _SHUTDOWN_WINDOW_SIGNALS)


async def _send_retryable_503(send: Send) -> None:
    """Emit a minimal retryable 503 so clients reconnect instead of erroring."""
    body = json.dumps(
        {
            "error": "server_restarting",
            "detail": "MCP server is restarting; retry shortly.",
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 503,
            "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", _RETRY_AFTER_SECONDS.encode("ascii")),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _header_value(scope: dict[str, Any], name: str) -> str | None:
    target = name.lower().encode("ascii")
    for raw_key, raw_value in scope.get("headers", ()):
        if raw_key.lower() == target:
            return raw_value.decode("utf-8", errors="replace").strip() or None
    return None


def wrap_streamable_http_app(app: ASGIApp) -> ASGIApp:
    """Wrap a Streamable HTTP ASGI app with project-root middleware."""
    return TappsProjectRootMiddleware(app)
