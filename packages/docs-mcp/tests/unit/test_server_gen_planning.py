"""Tests for the planning generation handlers (TAP-5608).

``server_gen_tools.py`` was split into per-family sibling modules. These tests
pin the contract the split had to preserve: each handler is owned by its family
module, the facade re-exports the identical object, and ``register()`` still
registers each tool under its own name.
"""

from __future__ import annotations

import inspect

import pytest
from mcp.server.fastmcp import FastMCP

from docs_mcp import server_gen_planning, server_gen_tools

HANDLERS = ("docs_generate_epic", "docs_generate_story", "docs_generate_prompt")


class TestPlanningHandlers:
    """Epic, story, and prompt generators moved to ``server_gen_planning``."""

    @pytest.mark.parametrize("name", HANDLERS)
    def test_handler_is_async_and_owned_by_family_module(self, name: str) -> None:
        fn = getattr(server_gen_planning, name)
        assert inspect.iscoroutinefunction(fn)
        assert fn.__module__ == "docs_mcp.server_gen_planning"

    @pytest.mark.parametrize("name", HANDLERS)
    def test_facade_reexports_the_same_object(self, name: str) -> None:
        assert getattr(server_gen_tools, name) is getattr(server_gen_planning, name)

    def test_register_registers_exactly_the_requested_tools(self) -> None:
        mcp = FastMCP("test-planning")
        server_gen_tools.register(mcp, frozenset(HANDLERS))
        assert sorted(mcp._tool_manager._tools) == sorted(HANDLERS)
