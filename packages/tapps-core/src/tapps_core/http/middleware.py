"""ASGI middleware for HTTP MCP fleet project-root routing."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Awaitable, Callable, MutableMapping
from pathlib import Path
from typing import Any

import structlog

from tapps_core.http.auth import (
    AUTHORIZATION_HEADER,
    FLEET_CREDENTIAL_HEADER,
    FleetAuthConfig,
    extract_presented_token,
)
from tapps_core.http.request_context import (
    PROJECT_ROOT_HEADER,
    reset_request_auth_scope,
    reset_request_project_root,
    set_request_auth_scope,
    set_request_project_root,
)

logger = structlog.get_logger(__name__)

# Match the ASGI spec (and Starlette): messages and scope are MutableMapping,
# not dict — using dict here makes real ASGI apps fail contravariance checks.
Message = MutableMapping[str, Any]
Send = Callable[[Message], Awaitable[None]]
Receive = Callable[[], Awaitable[Message]]
ASGIApp = Callable[[Message, Receive, Send], Awaitable[None]]

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

    async def __call__(self, scope: Message, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        header_value = _header_value(scope, PROJECT_ROOT_HEADER)
        token = None
        if header_value:
            with contextlib.suppress(OSError):
                token = set_request_project_root(Path(header_value))
        response_started = False

        async def _send(message: Message) -> None:
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


def _header_value(scope: Message, name: str) -> str | None:
    target = name.lower().encode("ascii")
    for raw_key, raw_value in scope.get("headers", ()):
        if raw_key.lower() == target:
            return raw_value.decode("utf-8", errors="replace").strip() or None
    return None


class TappsFleetAuthMiddleware:
    """Reject fleet requests that do not present a configured bearer token.

    Sits *outside* :class:`TappsProjectRootMiddleware` so an unauthenticated
    request never reaches the MCP app at all -- not even to have its
    ``X-Tapps-Project-Root`` header bound.
    """

    def __init__(self, app: ASGIApp, config: FleetAuthConfig) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope: Message, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or not self.config.enabled:
            await self.app(scope, receive, send)
            return

        presented = extract_presented_token(_scope_headers(scope))
        auth_scope = self.config.authenticate(presented)
        if auth_scope is None:
            logger.warning(
                "http.auth_rejected",
                path=scope.get("path"),
                credential_presented=bool(presented),
            )
            await _send_unauthorized(send)
            return

        scope_token = set_request_auth_scope(auth_scope)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_request_auth_scope(scope_token)


async def _send_unauthorized(send: Send) -> None:
    """Emit a 401 with a ``WWW-Authenticate`` challenge and no detail leak."""
    body = json.dumps(
        {
            "error": "unauthorized",
            "detail": (
                "This TappsMCP fleet endpoint requires a bearer token. Send it as "
                f"'{AUTHORIZATION_HEADER}: Bearer <token>' or '{FLEET_CREDENTIAL_HEADER}: <token>'."
            ),
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer realm="tapps-fleet"'),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _scope_headers(scope: Message) -> dict[str, str]:
    return {
        raw_key.decode("ascii", errors="replace"): raw_value.decode("utf-8", errors="replace")
        for raw_key, raw_value in scope.get("headers", ())
    }


def wrap_streamable_http_app(app: ASGIApp, *, auth: FleetAuthConfig | None = None) -> ASGIApp:
    """Wrap a Streamable HTTP ASGI app with fleet auth + project-root middleware."""
    wrapped: ASGIApp = TappsProjectRootMiddleware(app)
    if auth is not None and auth.enabled:
        wrapped = TappsFleetAuthMiddleware(wrapped, auth)
    return wrapped
