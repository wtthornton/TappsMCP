"""TAP-8160: session state must be scoped per project_root, not one flag.

Split out of ``test_session_auto_init.py`` so this dedicated coverage doesn't
grow that already-large file (kept the pre-existing test/param signature
fixes there minimal to avoid a quality-gate ratchet regression on a file this
change does not otherwise need to touch).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_helpers import (
    _reset_session_state,
    ensure_session_initialized,
    get_session_context,
    mark_session_initialized,
)


def _profile_mock() -> MagicMock:
    return MagicMock(project_type="library", has_tests=True, has_docker=False, has_ci=True)


class TestMultiProjectSessionState:
    """Uses only the base (pre-fix) call surface -- no-arg ``get_session_context()``
    -- so VAL-8160a is RED against the unfixed module-global-flag
    implementation for a domain reason (wrong project's settings observed),
    not an ImportError or signature mismatch.
    """

    @pytest.mark.asyncio
    async def test_two_projects_one_process_get_own_settings(self, tmp_path):
        """VAL-8160a: project B must not inherit project A's cached settings."""
        _reset_session_state()
        project_a = tmp_path / "project_a"
        project_b = tmp_path / "project_b"
        project_a.mkdir()
        project_b.mkdir()
        settings_a = MagicMock(project_root=project_a, quality_preset="strict")
        settings_b = MagicMock(project_root=project_b, quality_preset="lenient")

        with patch(
            "tapps_mcp.project.profiler.detect_project_profile",
            return_value=_profile_mock(),
        ):
            with patch("tapps_core.config.settings.load_settings", return_value=settings_a):
                await ensure_session_initialized()
                assert get_session_context()["quality_preset"] == "strict"

            with patch("tapps_core.config.settings.load_settings", return_value=settings_b):
                # Base defect: `_session_initialized` is already True from A,
                # so this call short-circuits and B's request is served A's
                # cached quality_preset instead of its own.
                await ensure_session_initialized()
                assert get_session_context()["quality_preset"] == "lenient"

    @pytest.mark.asyncio
    async def test_a_then_b_then_a_preserves_a_state(self, tmp_path):
        """VAL-8160b: re-entering A after B must not have erased A's entry.

        A naive fix that rebinds per request but still unconditionally clears
        the whole cache on every switch (the exact trap TAP-7948's fix had to
        avoid) would pass a check that only asserts on ``quality_preset``,
        because ``ensure_session_initialized`` would just recompute the same
        value from the still-mocked settings. So this asserts on a value that
        recompute does NOT produce -- ``custom_marker``, attached to A's
        cached entry out-of-band -- which only survives if A's dict entry
        itself was never dropped. What would make this FAIL: any
        implementation that clears/replaces the per-key entry (not just adds
        to it) when binding a *different* key, even transiently.
        """
        _reset_session_state()
        project_a = tmp_path / "project_a"
        project_b = tmp_path / "project_b"
        project_a.mkdir()
        project_b.mkdir()
        settings_a = MagicMock(project_root=project_a, quality_preset="strict")
        settings_b = MagicMock(project_root=project_b, quality_preset="lenient")

        with patch(
            "tapps_mcp.project.profiler.detect_project_profile",
            return_value=_profile_mock(),
        ):
            with patch("tapps_core.config.settings.load_settings", return_value=settings_a):
                await ensure_session_initialized()
                # Out-of-band marker on A's entry that a fresh recompute of A
                # would never re-produce -- only survival of the original
                # dict entry carries it forward.
                mark_session_initialized({"custom_marker": "keep-me"})

            with patch("tapps_core.config.settings.load_settings", return_value=settings_b):
                await ensure_session_initialized()

            with patch("tapps_core.config.settings.load_settings", return_value=settings_a):
                await ensure_session_initialized()
                ctx_a_again = get_session_context()

        assert ctx_a_again["quality_preset"] == "strict"
        assert ctx_a_again["custom_marker"] == "keep-me"
