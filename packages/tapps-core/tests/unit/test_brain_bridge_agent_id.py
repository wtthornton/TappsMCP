"""TAP-5896 (remainder): in-process AgentBrain must never receive a hardcoded
``agent_id`` literal.

Box 1 and box 3 of TAP-5896 are already satisfied on this base (the
constructor at ``create_brain_bridge`` already calls
``get_stable_agent_id(settings)`` — Ruling 9 / TAP-6701, commit e23f0f5d,
PR #309). This file closes the sole remaining open box: a regression test
that asserts the actual ``agent_id`` value passed to ``AgentBrain(...)``,
not merely "was called."

Deliberately its own file, not an addition to test_brain_bridge.py — that
file's own ratchet score regresses on any growth (L7 finding).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_settings() -> MagicMock:
    settings = MagicMock()
    settings.memory.database_url = "postgresql://x/db"
    settings.memory.profile = "repo-brain"
    settings.memory.hive_dsn = ""
    settings.memory.project_id = ""
    settings.memory.pg_pool_max_waiting = 0
    settings.memory.pg_pool_max_lifetime_seconds = 0
    return settings


class TestAgentIdNotHardcoded:
    def test_agent_id_not_hardcoded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The in-process AgentBrain constructor must receive the resolved
        stable agent id — not the pre-TAP-6701 literal ``"tapps-mcp"``, and
        not any other hardcoded string, regardless of what a default project
        slug elsewhere happens to look like.
        """
        monkeypatch.setenv("CLAUDE_AGENT_ID", "known-test-agent-id-72fda1")
        monkeypatch.setenv("TAPPS_BRAIN_DATABASE_URL", "postgresql://x/db")
        monkeypatch.delenv("TAPPS_BRAIN_PROJECT", raising=False)

        from tapps_core.brain_bridge import create_brain_bridge

        mock_brain = MagicMock()
        mock_brain.store.count.return_value = 0

        with patch("tapps_brain.AgentBrain", return_value=mock_brain) as mock_agent_brain:
            create_brain_bridge(settings=_make_settings())

        mock_agent_brain.assert_called_once()
        assert mock_agent_brain.call_args.kwargs["agent_id"] == "known-test-agent-id-72fda1"
