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
