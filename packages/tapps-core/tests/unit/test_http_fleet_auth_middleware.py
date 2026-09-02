"""Fleet auth middleware: 401 before the MCP app sees anything (TAP-6062)."""

from __future__ import annotations

from typing import Any

import pytest

from tapps_core.http.auth import SCOPE_OPERATOR, SCOPE_RUNTIME, FleetAuthConfig
from tapps_core.http.middleware import TappsFleetAuthMiddleware, wrap_streamable_http_app
from tapps_core.http.request_context import get_request_auth_scope


async def _receive() -> dict[str, Any]:
    return {"type": "http.request", "body": b"", "more_body": False}


def _scope(headers: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "type": "http",
        "path": "/mcp",
        "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()],
    }


class _Recorder:
    """Minimal ASGI app that records whether it was reached."""

    def __init__(self) -> None:
        self.calls = 0
        self.scopes: list[str | None] = []

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.calls += 1
        self.scopes.append(get_request_auth_scope())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _run(app: Any, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(_scope(headers), _receive, send)
    return sent


@pytest.mark.asyncio
class TestFleetAuthMiddleware:
    async def test_missing_token_is_401_and_app_never_runs(self) -> None:
        app = _Recorder()
        middleware = TappsFleetAuthMiddleware(app, FleetAuthConfig(operator_token="op"))

        sent = await _run(middleware)

        start = next(m for m in sent if m["type"] == "http.response.start")
        assert start["status"] == 401
        assert dict(start["headers"])[b"www-authenticate"] == b'Bearer realm="tapps-fleet"'
        assert app.calls == 0

    async def test_bad_token_is_401(self) -> None:
        app = _Recorder()
        middleware = TappsFleetAuthMiddleware(app, FleetAuthConfig(operator_token="op"))

        sent = await _run(middleware, {"Authorization": "Bearer wrong"})

        start = next(m for m in sent if m["type"] == "http.response.start")
        assert start["status"] == 401
        assert app.calls == 0

    async def test_good_token_binds_scope_and_reaches_app(self) -> None:
        app = _Recorder()
        middleware = TappsFleetAuthMiddleware(app, FleetAuthConfig(operator_token="op"))

        sent = await _run(middleware, {"Authorization": "Bearer op"})

        start = next(m for m in sent if m["type"] == "http.response.start")
        assert start["status"] == 200
        assert app.scopes == [SCOPE_OPERATOR]
        assert get_request_auth_scope() is None

    async def test_runtime_token_binds_runtime_scope(self) -> None:
        app = _Recorder()
        config = FleetAuthConfig(operator_token="op", runtime_token="rt", allow_runtime_scope=True)
        middleware = TappsFleetAuthMiddleware(app, config)

        await _run(middleware, {"X-Tapps-Fleet-Token": "rt"})

        assert app.scopes == [SCOPE_RUNTIME]

    async def test_runtime_token_rejected_on_non_runtime_server(self) -> None:
        app = _Recorder()
        config = FleetAuthConfig(operator_token="op", runtime_token="rt", allow_runtime_scope=False)
        middleware = TappsFleetAuthMiddleware(app, config)

        sent = await _run(middleware, {"X-Tapps-Fleet-Token": "rt"})

        assert next(m for m in sent if m["type"] == "http.response.start")["status"] == 401
        assert app.calls == 0

    async def test_auth_disabled_passes_through_unchanged(self) -> None:
        app = _Recorder()
        wrapped = wrap_streamable_http_app(app, auth=FleetAuthConfig())

        sent = await _run(wrapped)

        assert next(m for m in sent if m["type"] == "http.response.start")["status"] == 200
        assert app.calls == 1

    async def test_wrap_installs_auth_when_enabled(self) -> None:
        app = _Recorder()
        wrapped = wrap_streamable_http_app(app, auth=FleetAuthConfig(operator_token="op"))

        sent = await _run(wrapped)

        assert next(m for m in sent if m["type"] == "http.response.start")["status"] == 401
        assert app.calls == 0
