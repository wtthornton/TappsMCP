"""Tests for host-agnostic Linear MCP tool names (TAP-5451 / TAP-5452)."""

from __future__ import annotations

import pytest

from tapps_mcp.pipeline.linear_mcp_names import (
    LINEAR_LIST_ISSUES_MATCHER,
    LINEAR_SAVE_ISSUE_MATCHER,
    bash_case_pattern,
    is_linear_plugin_tool,
    linear_plugin_hint_phrasing,
    linear_plugin_matcher,
    linear_plugin_tool_names,
    matcher_covers_linear_leaf,
    patch_linear_hook_matchers,
)


class TestLinearPluginToolNames:
    def test_list_issues_includes_legacy_and_claude_ai(self) -> None:
        names = linear_plugin_tool_names("list_issues")
        assert "mcp__plugin_linear_linear__list_issues" in names
        assert "mcp__claude_ai_Linear__list_issues" in names
        assert "list_issues" in names

    def test_matcher_is_pipe_joined(self) -> None:
        m = linear_plugin_matcher("list_issues")
        assert "mcp__plugin_linear_linear__list_issues" in m
        assert "mcp__claude_ai_Linear__list_issues" in m
        assert "|" in m
        assert LINEAR_LIST_ISSUES_MATCHER == m

    def test_save_issue_matcher_distinct(self) -> None:
        assert "save_issue" in LINEAR_SAVE_ISSUE_MATCHER
        assert "list_issues" not in LINEAR_SAVE_ISSUE_MATCHER


class TestIsLinearPluginTool:
    @pytest.mark.parametrize(
        "name,leaf,expected",
        [
            ("mcp__plugin_linear_linear__list_issues", "list_issues", True),
            ("mcp__claude_ai_Linear__list_issues", "list_issues", True),
            ("mcp__cursor_Linear__list_issues", "list_issues", True),  # future host
            ("list_issues", "list_issues", True),
            ("mcp__plugin_linear_linear__save_issue", "save_issue", True),
            ("mcp__plugin_linear_linear__save_issue", "list_issues", False),
            ("mcp__nlt-build__tapps_quick_check", "list_issues", False),
            ("mcp__other_server__list_issues", "list_issues", False),
        ],
    )
    def test_classification(self, name: str, leaf: str, expected: bool) -> None:
        assert is_linear_plugin_tool(name, leaf) is expected


class TestMatcherCovers:
    def test_exact_legacy(self) -> None:
        assert matcher_covers_linear_leaf(
            ["mcp__plugin_linear_linear__list_issues"], "list_issues"
        )

    def test_pipe_matcher(self) -> None:
        assert matcher_covers_linear_leaf([LINEAR_LIST_ISSUES_MATCHER], "list_issues")

    def test_does_not_cover_unrelated(self) -> None:
        assert not matcher_covers_linear_leaf(["Bash", "Edit|Write"], "list_issues")


class TestHintsAndBash:
    def test_hint_does_not_hardcode_plugin_prefix(self) -> None:
        hint = linear_plugin_hint_phrasing("list_issues")
        assert "mcp__plugin_linear_linear__" not in hint
        assert "list_issues" in hint

    def test_bash_case_includes_both_hosts(self) -> None:
        pat = bash_case_pattern("list_issues")
        assert "mcp__plugin_linear_linear__list_issues" in pat
        assert "mcp__claude_ai_Linear__list_issues" in pat


class TestPatchLinearHookMatchers:
    def test_expands_pipe_matcher_to_per_host_entries(self) -> None:
        cfg: dict[str, list[dict[str, object]]] = {
            "PreToolUse": [
                {
                    "matcher": "__LINEAR_LIST_ISSUES_MATCHER__",
                    "hooks": [{"type": "command", "command": "x"}],
                }
            ]
        }
        patch_linear_hook_matchers(cfg)
        matchers = [e["matcher"] for e in cfg["PreToolUse"]]
        assert "mcp__plugin_linear_linear__list_issues" in matchers
        assert "mcp__claude_ai_Linear__list_issues" in matchers
        assert all("|" not in str(m) for m in matchers)
