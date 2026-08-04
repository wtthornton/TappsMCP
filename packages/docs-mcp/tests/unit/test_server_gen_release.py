"""Tests for the release generation handlers (TAP-5608).

``server_gen_tools.py`` was split into per-family sibling modules. These tests
pin the contract the split had to preserve: each handler is owned by its family
module, the facade re-exports the identical object, and ``register()`` still
registers each tool under its own name.
"""

from __future__ import annotations

import inspect

import pytest
from mcp.server.fastmcp import FastMCP

from docs_mcp import server_gen_release, server_gen_tools

HANDLERS = (
    "docs_generate_changelog",
    "docs_generate_release_notes",
    "docs_generate_release_update",
)


class TestReleaseHandlers:
    """Changelog, release-notes, and release-update generators."""

    @pytest.mark.parametrize("name", HANDLERS)
    def test_handler_is_async_and_owned_by_family_module(self, name: str) -> None:
        fn = getattr(server_gen_release, name)
        assert inspect.iscoroutinefunction(fn)
        assert fn.__module__ == "docs_mcp.server_gen_release"

    @pytest.mark.parametrize("name", HANDLERS)
    def test_facade_reexports_the_same_object(self, name: str) -> None:
        assert getattr(server_gen_tools, name) is getattr(server_gen_release, name)

    def test_register_registers_exactly_the_requested_tools(self) -> None:
        mcp = FastMCP("test-release")
        server_gen_tools.register(mcp, frozenset(HANDLERS))
        assert sorted(mcp._tool_manager._tools) == sorted(HANDLERS)
