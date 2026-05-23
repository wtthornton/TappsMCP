"""TAP-1991: Assert deprecation notices present in tapps_memory docstring.

Every sub-action in _VALID_ACTIONS must carry a [DEPRECATED 2026-Q3 — use
mcp__tapps-brain__<tool>] prefix in the Actions: block of the tapps_memory
docstring so Claude's tool catalog signals the migration target.
"""

from __future__ import annotations

import inspect

import pytest

from tapps_mcp.server_memory_tools import _VALID_ACTIONS, tapps_memory


class TestDeprecationNotices:
    """TAP-1991: tapps_memory docstring must carry deprecation tags for all actions."""

    def _get_docstring(self) -> str:
        doc = inspect.getdoc(tapps_memory)
        assert doc is not None, "tapps_memory has no docstring"
        return doc

    def test_top_level_deprecation_notice_present(self) -> None:
        """Main tool description must carry the top-level [DEPRECATED] notice."""
        doc = self._get_docstring()
        assert "[DEPRECATED 2026-Q3" in doc, (
            "tapps_memory docstring is missing top-level deprecation notice. "
            "Expected '[DEPRECATED 2026-Q3' near the start of the docstring."
        )

    def test_top_level_notice_references_brain_tools(self) -> None:
        """Top-level deprecation notice must name the mcp__tapps-brain__ namespace."""
        doc = self._get_docstring()
        assert "mcp__tapps-brain__" in doc, (
            "tapps_memory docstring must reference mcp__tapps-brain__* as the migration target."
        )

    @pytest.mark.parametrize("action", sorted(_VALID_ACTIONS))
    def test_action_has_deprecation_prefix(self, action: str) -> None:
        """Each action in _VALID_ACTIONS must have a [DEPRECATED 2026-Q3] prefix in the Actions: block."""
        doc = self._get_docstring()
        # The Actions: block uses "        action_name: [DEPRECATED..." format.
        # We check for the action name followed by the deprecation tag anywhere in the doc.
        deprecated_marker = f"{action}: [DEPRECATED 2026-Q3"
        assert deprecated_marker in doc, (
            f"Action '{action}' is missing the deprecation prefix in the tapps_memory docstring. "
            f"Expected to find '{deprecated_marker}' in the Actions: block."
        )

    @pytest.mark.parametrize("action", sorted(_VALID_ACTIONS))
    def test_action_deprecation_names_brain_tool(self, action: str) -> None:
        """Each action's deprecation line must name a specific mcp__tapps-brain__ target."""
        doc = self._get_docstring()
        # Find the line with this action's deprecation tag.
        deprecated_marker = f"{action}: [DEPRECATED 2026-Q3"
        idx = doc.find(deprecated_marker)
        assert idx != -1, f"Action '{action}' missing deprecation prefix (checked in parametrize above)"
        # Extract up to 120 chars from the action description line to find the brain tool name.
        snippet = doc[idx : idx + 120]
        assert "mcp__tapps-brain__" in snippet, (
            f"Action '{action}' deprecation line does not name a mcp__tapps-brain__* replacement. "
            f"Found: {snippet!r}"
        )

    def test_all_valid_actions_covered(self) -> None:
        """Smoke test: _VALID_ACTIONS is non-empty and all expected CRUD actions are present."""
        assert len(_VALID_ACTIONS) >= 33, (
            f"Expected at least 33 actions in _VALID_ACTIONS, got {len(_VALID_ACTIONS)}"
        )
        expected_core = {"save", "get", "search", "delete", "list", "reinforce"}
        assert expected_core <= _VALID_ACTIONS, (
            f"Core CRUD actions missing from _VALID_ACTIONS: {expected_core - _VALID_ACTIONS}"
        )
