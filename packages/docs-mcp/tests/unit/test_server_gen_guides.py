"""Tests for the guide generation handlers (TAP-5608).

``server_gen_tools.py`` was split into per-family sibling modules. These tests
pin the contract the split had to preserve: each handler is owned by its family
module, the facade re-exports the identical object, and ``register()`` still
registers each tool under its own name.
"""

from __future__ import annotations

import inspect

import pytest
from mcp.server.fastmcp import FastMCP

from docs_mcp import server_gen_guides, server_gen_tools

HANDLERS = (
    "docs_generate_onboarding",
    "docs_generate_contributing",
    "docs_generate_runbook",
    "docs_generate_postmortem",
    "docs_generate_prd",
)


class TestGuideHandlers:
    """Onboarding, contributing, runbook, postmortem, and PRD generators."""

    @pytest.mark.parametrize("name", HANDLERS)
    def test_handler_is_async_and_owned_by_family_module(self, name: str) -> None:
        fn = getattr(server_gen_guides, name)
        assert inspect.iscoroutinefunction(fn)
        assert fn.__module__ == "docs_mcp.server_gen_guides"

    @pytest.mark.parametrize("name", HANDLERS)
    def test_facade_reexports_the_same_object(self, name: str) -> None:
        assert getattr(server_gen_tools, name) is getattr(server_gen_guides, name)

    def test_register_registers_exactly_the_requested_tools(self) -> None:
        mcp = FastMCP("test-guides")
        server_gen_tools.register(mcp, frozenset(HANDLERS))
        assert sorted(mcp._tool_manager._tools) == sorted(HANDLERS)
