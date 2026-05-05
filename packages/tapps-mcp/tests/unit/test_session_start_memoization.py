"""TAP-1379: tapps_session_start memoizes per MCP server process.

Audit (2026-05-04 metrics) showed ~307 tapps_session_start calls across 29
distinct sessions in one day — ~23 calls per session. The Claude Code
SessionStart hook re-fires on resume/compact, and agents defensively re-call
the tool. Both layers are addressed:

- Tool layer (this test): per-process cache keyed by MetricsHub _SESSION_ID.
  Repeat calls within the same process return the cached response with a
  ``cached: true`` marker. ``force=True`` bypasses the cache.
- Hook layer (separate file): per-Claude-session sentinel suppresses the
  REQUIRED prompt on subsequent SessionStart fires.
"""

from __future__ import annotations

import pytest

from tapps_mcp.server_pipeline_tools import _reset_session_start_cache
from tapps_mcp.tools.checklist import CallTracker


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    _reset_session_start_cache()
    CallTracker.reset()


class TestSessionStartMemoization:
    @pytest.mark.asyncio
    async def test_second_call_returns_cached(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        first = await tapps_session_start()
        assert first["success"] is True
        assert first["data"].get("cached") is not True

        second = await tapps_session_start()
        assert second["success"] is True
        assert second["data"].get("cached") is True
        # Same response shape, just marked cached.
        assert second["tool"] == "tapps_session_start"
        assert second["data"]["server"] == first["data"]["server"]

    @pytest.mark.asyncio
    async def test_force_true_bypasses_cache(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        await tapps_session_start()
        forced = await tapps_session_start(force=True)
        # force re-runs the full bootstrap, so no cached marker.
        assert forced["data"].get("cached") is not True
        assert forced["success"] is True

    @pytest.mark.asyncio
    async def test_quick_and_full_cached_independently(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        full = await tapps_session_start()
        quick = await tapps_session_start(quick=True)

        # Each is the first call for its (session_id, quick) key, so neither
        # should be marked cached.
        assert full["data"].get("cached") is not True
        assert quick["data"].get("cached") is not True

        # Repeat calls hit their respective cache slots.
        full2 = await tapps_session_start()
        quick2 = await tapps_session_start(quick=True)
        assert full2["data"].get("cached") is True
        assert quick2["data"].get("cached") is True

    @pytest.mark.asyncio
    async def test_cached_response_is_fast(self) -> None:
        """A cached call should return in well under the full-init budget."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        await tapps_session_start()
        cached = await tapps_session_start()
        # The cached path records elapsed_ms at the data top-level.
        assert "elapsed_ms" in cached["data"]
        # Hard ceiling: 50ms is generous (no subprocess, no Brain probe).
        assert cached["data"]["elapsed_ms"] < 50

    @pytest.mark.asyncio
    async def test_reset_cache_helper_clears_state(self) -> None:
        from tapps_mcp.server_pipeline_tools import (
            _reset_session_start_cache,
            tapps_session_start,
        )

        await tapps_session_start()
        cached = await tapps_session_start()
        assert cached["data"].get("cached") is True

        _reset_session_start_cache()
        fresh = await tapps_session_start()
        assert fresh["data"].get("cached") is not True


class TestSessionStartHookSentinel:
    """Hook-layer short-circuit: the SessionStart shell hook must skip its
    REQUIRED prompt after the first fire for a given Claude session_id."""

    def test_hook_template_writes_and_checks_sentinel(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOK_SCRIPTS

        script = CLAUDE_HOOK_SCRIPTS["tapps-session-start.sh"]
        # Sentinel path uses the Claude session_id parsed from the JSON input.
        assert ".session-start-fired-" in script
        # Must short-circuit (exit 0 with no echo) when sentinel exists.
        assert 'if [ -f "$SENTINEL" ]' in script
        # Still emits the REQUIRED prompt on first fire for a session.
        assert "REQUIRED: Call tapps_session_start()" in script

    def test_hook_emits_prompt_on_first_fire_and_silences_on_resume(
        self, tmp_path: object
    ) -> None:
        """End-to-end: run the deployed hook script with a fake session_id."""
        import os
        import shutil
        import subprocess
        from pathlib import Path

        from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOK_SCRIPTS

        if shutil.which("bash") is None:
            pytest.skip("bash not available")

        tmpdir = Path(str(tmp_path))
        script_path = tmpdir / "tapps-session-start.sh"
        script_path.write_text(CLAUDE_HOOK_SCRIPTS["tapps-session-start.sh"])
        script_path.chmod(0o755)

        env = {**os.environ, "TAPPS_PROJECT_ROOT": str(tmpdir)}
        payload = '{"session_id":"abc123fake"}'

        first = subprocess.run(
            ["bash", str(script_path)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert first.returncode == 0
        assert "REQUIRED" in first.stdout

        sentinel = tmpdir / ".tapps-mcp" / ".session-start-fired-abc123fake"
        assert sentinel.exists()

        second = subprocess.run(
            ["bash", str(script_path)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert second.returncode == 0
        assert second.stdout.strip() == ""

        # Different session_id => prompt fires again.
        third = subprocess.run(
            ["bash", str(script_path)],
            input='{"session_id":"different456"}',
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert third.returncode == 0
        assert "REQUIRED" in third.stdout
