"""Tests for tapps_core.brain_bridge_errors — constants, helpers, exceptions.

Split out of test_brain_bridge.py alongside the TAP-6736 megafile split.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from tapps_core.brain_bridge_errors import (
    BrainMcpError,
    ProfileMismatchError,
    ToolNotInProfileError,
    _classify_mcp_error,
    _parse_out_of_profile_message,
    _raise_with_body,
    _tenant_override_headers,
    get_bridge_used_tools,
    register_bridge_used_tools,
)


class TestTenantOverrideHeaders:
    def test_empty_project_id_yields_no_header(self) -> None:
        assert _tenant_override_headers(None) == {}
        assert _tenant_override_headers("  ") == {}

    def test_project_id_is_stripped_and_wrapped(self) -> None:
        assert _tenant_override_headers(" proj-1 ") == {"X-Project-Id": "proj-1"}


class TestRaiseWithBody:
    def test_no_raise_below_400(self) -> None:
        response = MagicMock(status_code=200)
        _raise_with_body(response, "some_tool")  # must not raise

    def test_raises_with_body_on_error(self) -> None:
        response = MagicMock(status_code=400, text='{"error": "bad_request"}')
        try:
            _raise_with_body(response, "memory_save")
        except RuntimeError as exc:
            assert "400" in str(exc)
            assert "memory_save" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")


class TestParseOutOfProfileMessage:
    def test_parses_canonical_message(self) -> None:
        result = _parse_out_of_profile_message("Tool 'memory_save' is not available in profile 'reviewer'.")
        assert result == ("memory_save", "reviewer")

    def test_returns_none_on_no_match(self) -> None:
        assert _parse_out_of_profile_message("something else entirely") is None


class TestClassifyMcpError:
    def test_tool_not_in_profile_is_gated(self) -> None:
        exc = ToolNotInProfileError("denied", tool="memory_save", profile="reviewer")
        assert _classify_mcp_error(exc) == "gated"

    def test_unknown_tool_is_removed(self) -> None:
        exc = BrainMcpError("Unknown tool: foo")
        assert _classify_mcp_error(exc) == "removed"

    def test_other_exception_is_other(self) -> None:
        assert _classify_mcp_error(RuntimeError("network timeout")) == "other"

    def test_profile_mismatch_error_is_gated(self) -> None:
        exc = ProfileMismatchError("denied", tool="memory_save", profile="reviewer")
        assert _classify_mcp_error(exc) == "gated"


class TestBridgeUsedToolsRegistry:
    def test_register_and_get_roundtrip(self) -> None:
        register_bridge_used_tools({"memory_save", "memory_get"})
        try:
            assert get_bridge_used_tools() == frozenset({"memory_save", "memory_get"})
        finally:
            # Restore the module default so other tests aren't affected.
            from tapps_core import brain_bridge_errors

            register_bridge_used_tools(brain_bridge_errors._BRIDGE_USED_TOOLS_SNAPSHOT)

    def test_dunder_alias_matches_get_bridge_used_tools(self) -> None:
        import tapps_core.brain_bridge as bb

        assert get_bridge_used_tools() == bb._BRIDGE_USED_TOOLS
