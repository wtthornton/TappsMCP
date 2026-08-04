"""Tests for scripts/tool_budget_lint.py — the MCP tool-budget guards.

Covers the TAP-5611 documented-count check: the front-door docs must state the
tool counts the registry actually has. The counts drifted twice before this
guard existed (TAP-4577, then TAP-5611), both times unnoticed for months.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPO_ROOT / "scripts" / "tool_budget_lint.py"


@pytest.fixture(scope="module")
def lint() -> ModuleType:
    """Import scripts/tool_budget_lint.py (outside the installed packages)."""
    spec = importlib.util.spec_from_file_location("tool_budget_lint", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["tool_budget_lint"] = module
    spec.loader.exec_module(module)
    return module


class TestCountRegisteredTools:
    def test_counts_both_servers(self, lint: ModuleType) -> None:
        counts = lint.count_registered_tools()
        assert set(counts) == {"tapps-mcp", "docs-mcp"}
        assert all(value > 0 for value in counts.values())

    def test_excludes_the_register_tool_definition(
        self, lint: ModuleType, tmp_path: Path
    ) -> None:
        pkg = tmp_path / "packages" / "tapps-mcp" / "src" / "tapps_mcp"
        pkg.mkdir(parents=True)
        (pkg / "mcp_register.py").write_text("def register_tool(mcp, fn):\n    ...\n")
        (pkg / "server.py").write_text("register_tool(mcp, one)\nregister_tool(mcp, two)\n")
        (tmp_path / "packages" / "docs-mcp" / "src" / "docs_mcp").mkdir(parents=True)

        assert lint.count_registered_tools(tmp_path)["tapps-mcp"] == 2


class TestCountAttribution:
    def test_diagram_counts_pair_with_the_names_above(self, lint: ModuleType) -> None:
        diagram = ["tapps-mcp      docs-mcp", "(44 tools)     (42 tools)"]
        assert lint._attribute_counts(diagram, 1) == [("tapps-mcp", 44), ("docs-mcp", 42)]

    def test_inline_count_binds_to_the_server_named_on_the_line(self, lint: ModuleType) -> None:
        line = ["| **docs-mcp** | `packages/docs-mcp/` | Documentation server (42 tools) |"]
        assert lint._attribute_counts(line, 0) == [("docs-mcp", 42)]

    def test_line_without_a_count_yields_nothing(self, lint: ModuleType) -> None:
        assert lint._attribute_counts(["tapps-mcp is an MCP server"], 0) == []

    def test_unattributable_count_is_skipped(self, lint: ModuleType) -> None:
        assert lint._attribute_counts(["", "(44 tools) (42 tools) (7 tools)"], 1) == []


class TestDocumentedCounts:
    def test_current_tree_is_consistent(self, lint: ModuleType) -> None:
        ok, message = lint.check_documented_counts()
        assert ok, message

    def test_wrong_per_server_count_fails(self, lint: ModuleType, tmp_path: Path) -> None:
        _fake_registry(tmp_path, tapps=44, docs=42)
        (tmp_path / "README.md").write_text("tapps-mcp (43 tools)\n")

        ok, message = lint.check_documented_counts(tmp_path)
        assert not ok
        assert "README.md:1 claims 43 tapps-mcp tools" in message

    def test_wrong_combined_count_fails(self, lint: ModuleType, tmp_path: Path) -> None:
        _fake_registry(tmp_path, tapps=44, docs=42)
        (tmp_path / "README.md").write_text("expose **85 tools** (43 TappsMCP + 42 DocsMCP)\n")

        ok, message = lint.check_documented_counts(tmp_path)
        assert not ok
        assert "claims 43 + 42" in message

    def test_combined_total_that_does_not_add_up_fails(
        self, lint: ModuleType, tmp_path: Path
    ) -> None:
        _fake_registry(tmp_path, tapps=44, docs=42)
        (tmp_path / "README.md").write_text("expose **85 tools** (44 TappsMCP + 42 DocsMCP)\n")

        ok, message = lint.check_documented_counts(tmp_path)
        assert not ok
        assert "totals 85" in message

    def test_correct_counts_pass(self, lint: ModuleType, tmp_path: Path) -> None:
        _fake_registry(tmp_path, tapps=44, docs=42)
        (tmp_path / "README.md").write_text(
            "expose **86 tools** (44 TappsMCP + 42 DocsMCP)\n\ntapps-mcp (44 tools)\n"
        )

        ok, message = lint.check_documented_counts(tmp_path)
        assert ok, message


class TestNewRegistrations:
    def test_register_tool_addition_needs_the_budget_doc(self, lint: ModuleType) -> None:
        diff = "+    register_tool(mcp_instance, tapps_new_thing, annotations=_ANN)\n"
        ok, message = lint.check_new_registrations(diff, ["packages/tapps-mcp/src/server.py"], "")
        assert not ok
        assert "tool-budget.md" in message

    def test_budget_doc_update_satisfies_the_gate(self, lint: ModuleType) -> None:
        diff = "+    register_tool(mcp_instance, tapps_new_thing, annotations=_ANN)\n"
        ok, _message = lint.check_new_registrations(diff, [lint._BUDGET_DOC], "")
        assert ok


def _fake_registry(root: Path, *, tapps: int, docs: int) -> None:
    """Write a minimal package tree with the requested registration counts."""
    for name, module, count in (
        ("tapps-mcp", "tapps_mcp", tapps),
        ("docs-mcp", "docs_mcp", docs),
    ):
        pkg = root / "packages" / name / "src" / module
        pkg.mkdir(parents=True)
        (pkg / "server.py").write_text("register_tool(mcp, fn)\n" * count)
