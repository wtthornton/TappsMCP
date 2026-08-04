"""Tests for the project-doc generation handlers (TAP-5608).

``server_gen_tools.py`` was split into per-family sibling modules. These tests
pin the contract the split had to preserve: each handler is owned by its family
module, the facade re-exports the identical object, and ``register()`` still
registers each tool under its own name.
"""

from __future__ import annotations

import inspect

import pytest
from mcp.server.fastmcp import FastMCP

from docs_mcp import server_gen_project, server_gen_tools

HANDLERS = (
    "docs_generate_readme",
    "docs_generate_api",
    "docs_generate_adr",
    "docs_generate_llms_txt",
    "docs_generate_frontmatter",
    "docs_generate_purpose",
    "docs_generate_doc_index",
)


class TestProjectHandlers:
    """README, API, ADR, llms.txt, frontmatter, purpose, and doc-index."""

    @pytest.mark.parametrize("name", HANDLERS)
    def test_handler_is_async_and_owned_by_family_module(self, name: str) -> None:
        fn = getattr(server_gen_project, name)
        assert inspect.iscoroutinefunction(fn)
        assert fn.__module__ == "docs_mcp.server_gen_project"

    @pytest.mark.parametrize("name", HANDLERS)
    def test_facade_reexports_the_same_object(self, name: str) -> None:
        assert getattr(server_gen_tools, name) is getattr(server_gen_project, name)

    def test_register_registers_exactly_the_requested_tools(self) -> None:
        mcp = FastMCP("test-project")
        server_gen_tools.register(mcp, frozenset(HANDLERS))
        assert sorted(mcp._tool_manager._tools) == sorted(HANDLERS)
