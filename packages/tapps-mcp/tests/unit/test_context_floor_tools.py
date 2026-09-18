"""Tests for scripts/context_floor_tools.py -- the MCP tool-schema measurement.

TAP-7770: ``register_tool(mcp_instance, session_start_impl, ..., name="tapps_session_start")``
in ``server_pipeline_tools.py`` passes a local variable (holding a dynamically resolved
handler) as the positional ``fn`` argument, with an explicit ``name=`` override. The tools
bucket used to read the positional argument's bare AST identifier as the registered tool
name -- "session_start_impl" -- ignoring the ``name=`` override that ``mcp_register.register_tool``
itself treats as authoritative (``tool_name = name or fn.__name__``). No module-level function
is ever named "session_start_impl", so ``find_tool_definitions`` raised and the whole report
aborted, silently discarding a healthy skills bucket. See ``context_floor_report.py`` for the
bucket-tolerance half of the fix.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture(scope="module", autouse=True)
def _scripts_on_path() -> None:
    """``context_floor_tools`` imports sibling ``context_floor_*`` modules by
    bare name (as ``measure_context_floor.py`` does), so scripts/ must be on
    sys.path before it is loaded."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(scope="module")
def tools_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "context_floor_tools", SCRIPTS_DIR / "context_floor_tools.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["context_floor_tools"] = module
    spec.loader.exec_module(module)
    return module


def _parse_call(source: str) -> ast.Call:
    """Parse a single expression statement and return its ``ast.Call`` node."""
    tree = ast.parse(source)
    (stmt,) = tree.body
    assert isinstance(stmt, ast.Expr)
    assert isinstance(stmt.value, ast.Call)
    return stmt.value


class TestRegisteredToolName:
    def test_explicit_name_kwarg_overrides_positional_identifier(
        self, tools_module: ModuleType
    ) -> None:
        """The exact TAP-7770 shape: a local-variable handler with an explicit
        ``name=`` override must resolve to the override, not the variable name."""
        call = _parse_call(
            'register_tool(mcp_instance, session_start_impl, '
            'annotations=ANNOT, name="tapps_session_start")'
        )
        assert tools_module._registered_tool_name(call) == "tapps_session_start"

    def test_plain_call_uses_positional_identifier(self, tools_module: ModuleType) -> None:
        """Regression guard: the common case (no ``name=`` override) is unchanged."""
        call = _parse_call("register_tool(mcp_instance, tapps_quick_check, annotations=ANNOT)")
        assert tools_module._registered_tool_name(call) == "tapps_quick_check"

    def test_non_string_name_kwarg_falls_back_to_positional(
        self, tools_module: ModuleType
    ) -> None:
        """A non-literal ``name=`` (e.g. a variable) can't be statically resolved --
        fall back to the positional identifier rather than crashing."""
        call = _parse_call(
            "register_tool(mcp_instance, some_handler, annotations=ANNOT, name=dynamic_name)"
        )
        assert tools_module._registered_tool_name(call) == "some_handler"

    def test_non_register_tool_call_returns_none(self, tools_module: ModuleType) -> None:
        call = _parse_call("some_other_function(mcp_instance, handler)")
        assert tools_module._registered_tool_name(call) is None


class TestSessionStartRegistration:
    """Integration-level: run the real detection against the real repo tree."""

    def test_session_start_impl_is_not_a_registered_tool_name(
        self, tools_module: ModuleType
    ) -> None:
        names = tools_module.find_registered_tool_names(tools_module._TOOL_ROOTS)
        assert "session_start_impl" not in names
        assert "tapps_session_start" in names

    def test_tapps_session_start_resolves_to_a_module_level_definition(
        self, tools_module: ModuleType
    ) -> None:
        names = tools_module.find_registered_tool_names(tools_module._TOOL_ROOTS)
        defs = tools_module.find_tool_definitions(tools_module._TOOL_ROOTS, names)
        path, node = defs["tapps_session_start"]
        assert path.name == "server_pipeline_tools.py"
        assert node.name == "tapps_session_start"
