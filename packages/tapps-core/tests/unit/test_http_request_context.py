"""Tests for HTTP request context (ADR-0024)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_core.http.middleware import TappsProjectRootMiddleware
from tapps_core.http.request_context import (
    PROJECT_ROOT_HEADER,
    get_request_project_root,
    reset_request_project_root,
    set_request_project_root,
)


class TestRequestProjectRootContext:
    def test_set_and_get(self, tmp_path: Path) -> None:
        token = set_request_project_root(tmp_path)
        try:
            assert get_request_project_root() == tmp_path.resolve()
        finally:
            reset_request_project_root(token)

    def test_reset_clears(self, tmp_path: Path) -> None:
        token = set_request_project_root(tmp_path)
        reset_request_project_root(token)
        assert get_request_project_root() is None


@pytest.mark.asyncio
async def test_middleware_binds_header(tmp_path: Path) -> None:
    seen: list[Path | None] = []

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        seen.append(get_request_project_root())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = TappsProjectRootMiddleware(app)
    scope = {
        "type": "http",
        "headers": [(PROJECT_ROOT_HEADER.encode(), str(tmp_path).encode())],
    }

    async def receive():  # type: ignore[no-untyped-def]
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):  # type: ignore[no-untyped-def]
        return None

    await middleware(scope, receive, send)
    assert seen == [tmp_path.resolve()]
    assert get_request_project_root() is None


def _http_scope() -> dict[str, object]:
    return {"type": "http", "headers": []}


async def _receive() -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {"type": "http.request", "body": b"", "more_body": False}


@pytest.mark.asyncio
async def test_shutdown_window_runtimeerror_becomes_503() -> None:
    """A request hitting the SDK shutdown window returns a retryable 503."""

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        raise RuntimeError("Task group is not initialized. Make sure to use run().")

    sent: list[dict[str, object]] = []

    async def send(message):  # type: ignore[no-untyped-def]
        sent.append(message)

    middleware = TappsProjectRootMiddleware(app)
    await middleware(_http_scope(), _receive, send)

    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 503
    headers = dict(start["headers"])
    assert headers[b"retry-after"] == b"1"
    assert headers[b"content-type"] == b"application/json"
    body = next(m for m in sent if m["type"] == "http.response.body")
    assert b"server_restarting" in body["body"]


@pytest.mark.asyncio
async def test_non_shutdown_runtimeerror_propagates() -> None:
    """Genuine RuntimeErrors must not be masked as a 503."""

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        raise RuntimeError("something genuinely broke")

    async def send(message):  # type: ignore[no-untyped-def]
        return None

    middleware = TappsProjectRootMiddleware(app)
    with pytest.raises(RuntimeError, match="something genuinely broke"):
        await middleware(_http_scope(), _receive, send)


@pytest.mark.asyncio
async def test_shutdown_error_after_response_started_propagates() -> None:
    """If the response already started we cannot double-send; re-raise."""

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        raise RuntimeError("Task group is not initialized. Make sure to use run().")

    async def send(message):  # type: ignore[no-untyped-def]
        return None

    middleware = TappsProjectRootMiddleware(app)
    with pytest.raises(RuntimeError, match="Task group is not initialized"):
        await middleware(_http_scope(), _receive, send)


@pytest.mark.asyncio
async def test_non_http_scope_passes_through() -> None:
    """Lifespan/websocket scopes bypass the HTTP shutdown guard untouched."""
    calls: list[str] = []

    async def app(scope, receive, send):  # type: ignore[no-untyped-def]
        calls.append(scope["type"])

    async def send(message):  # type: ignore[no-untyped-def]
        return None

    middleware = TappsProjectRootMiddleware(app)
    await middleware({"type": "lifespan"}, _receive, send)
    assert calls == ["lifespan"]
