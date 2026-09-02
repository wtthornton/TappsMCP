"""Workspace-free HTTP request mode (TAP-6062, Story 4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import tapps_core.config.settings as settings_mod
from tapps_core.config.settings import load_settings
from tapps_core.http.middleware import TappsProjectRootMiddleware
from tapps_core.http.request_context import (
    PROJECT_ROOT_HEADER,
    WORKSPACE_FREE_ROOT,
    is_http_request,
    mark_http_request,
    reset_http_request,
    reset_request_project_root,
    set_request_project_root,
    workspace_mode,
)


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Any:
    settings_mod._cached_settings = None
    yield
    settings_mod._cached_settings = None


class TestWorkspaceMode:
    def test_stdio_by_default(self) -> None:
        assert is_http_request() is False
        assert workspace_mode() == "stdio"

    def test_http_without_root_is_workspace_free(self) -> None:
        token = mark_http_request()
        try:
            assert workspace_mode() == "workspace-free"
        finally:
            reset_http_request(token)

    def test_http_with_root_is_scoped(self, tmp_path: Path) -> None:
        http_token = mark_http_request()
        root_token = set_request_project_root(tmp_path)
        try:
            assert workspace_mode() == "scoped"
        finally:
            reset_request_project_root(root_token)
            reset_http_request(http_token)

    def test_marker_is_distinct_from_absent_header(self, tmp_path: Path) -> None:
        """The header-absent ``None`` cannot express "an HTTP request is live"."""
        token = mark_http_request()
        try:
            from tapps_core.http.request_context import get_request_project_root

            assert get_request_project_root() is None
            assert is_http_request() is True
        finally:
            reset_http_request(token)


@pytest.mark.asyncio
class TestMiddlewareMarker:
    async def test_marker_set_even_without_project_root_header(self) -> None:
        seen: list[str] = []

        async def app(scope: Any, receive: Any, send: Any) -> None:
            seen.append(workspace_mode())

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            return None

        await TappsProjectRootMiddleware(app)({"type": "http", "headers": []}, receive, send)

        assert seen == ["workspace-free"]
        assert is_http_request() is False

    async def test_marker_cleared_after_request(self, tmp_path: Path) -> None:
        async def app(scope: Any, receive: Any, send: Any) -> None:
            assert workspace_mode() == "scoped"

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            return None

        scope = {
            "type": "http",
            "headers": [(PROJECT_ROOT_HEADER.encode(), str(tmp_path).encode())],
        }
        await TappsProjectRootMiddleware(app)(scope, receive, send)

        assert workspace_mode() == "stdio"


class TestLoadSettingsWorkspaceFree:
    def test_stdio_still_falls_back_to_cwd(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Unchanged behavior for stdio: CWD is the workspace."""
        monkeypatch.delenv("TAPPS_MCP_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)

        assert load_settings().project_root == tmp_path

    def test_workspace_free_request_does_not_use_cwd(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        monkeypatch.delenv("TAPPS_MCP_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)

        token = mark_http_request()
        try:
            resolved = load_settings().project_root
        finally:
            reset_http_request(token)

        assert resolved != tmp_path
        assert resolved == WORKSPACE_FREE_ROOT

    def test_workspace_free_request_ignores_env_root(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """The fleet's own TAPPS_MCP_PROJECT_ROOT is not the caller's workspace."""
        monkeypatch.setenv("TAPPS_MCP_PROJECT_ROOT", str(tmp_path))

        token = mark_http_request()
        try:
            resolved = load_settings().project_root
        finally:
            reset_http_request(token)

        assert resolved == WORKSPACE_FREE_ROOT

    def test_scoped_request_uses_the_header_root(self, tmp_path: Path, monkeypatch: Any) -> None:
        monkeypatch.delenv("TAPPS_MCP_PROJECT_ROOT", raising=False)

        http_token = mark_http_request()
        root_token = set_request_project_root(tmp_path)
        try:
            resolved = load_settings().project_root
        finally:
            reset_request_project_root(root_token)
            reset_http_request(http_token)

        assert resolved == tmp_path.resolve()

    def test_workspace_free_result_is_not_cached_into_the_singleton(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A fleet request must not pin later stdio callers to the empty root."""
        monkeypatch.delenv("TAPPS_MCP_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)

        token = mark_http_request()
        try:
            load_settings()
        finally:
            reset_http_request(token)

        assert settings_mod._cached_settings is None
        assert load_settings().project_root == tmp_path
