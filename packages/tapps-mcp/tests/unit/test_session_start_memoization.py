"""TAP-1379 / TAP-1928: tapps_session_start memoization and file-based sentinel.

Audit (2026-05-04 metrics) showed ~307 tapps_session_start calls across 29
distinct sessions in one day — ~23 calls per session. The Claude Code
SessionStart hook re-fires on resume/compact, and agents defensively re-call
the tool. Both layers are addressed:

- Tool layer (TAP-1379, TestSessionStartMemoization): per-process cache keyed
  by MetricsHub _SESSION_ID. Repeat calls within the same process return the
  cached response with a ``cached: true`` marker. ``force=True`` bypasses the
  cache.
- File sentinel layer (TAP-1928, TestSessionStartSentinel): persists across
  MCP server restarts. Sub-agents that start a fresh process skip the full
  bootstrap when ``.tapps-mcp/.tapps-session-id`` is younger than 3600 s.
- Hook layer (separate file): per-Claude-session sentinel suppresses the
  REQUIRED prompt on subsequent SessionStart fires.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.server_pipeline_tools import _reset_session_start_cache
from tapps_mcp.tools.checklist import CallTracker


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    from tapps_mcp.tools.session_start_core import SENTINEL_FILENAME

    _reset_session_start_cache()
    CallTracker.reset()
    # TAP-1928: also clear the file-based sentinel so that in-memory memoization
    # tests see a clean slate.  The sentinel is written by the full bootstrap, so
    # a prior test run (or the live MCP session) may have left it on disk.
    Path(".tapps-mcp").joinpath(SENTINEL_FILENAME).unlink(missing_ok=True)


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
        from tapps_mcp.tools.session_start_core import SENTINEL_FILENAME

        await tapps_session_start()
        cached = await tapps_session_start()
        assert cached["data"].get("cached") is True

        _reset_session_start_cache()
        # TAP-1928: also clear the file sentinel — resetting the in-memory cache
        # alone would still hit the on-disk sentinel written by the first call.
        Path(".tapps-mcp").joinpath(SENTINEL_FILENAME).unlink(missing_ok=True)
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
        assert "usage-gaps-hint" in script

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


# ---------------------------------------------------------------------------
# TAP-1928: file-based sentinel unit tests
# ---------------------------------------------------------------------------


class TestReadWriteSessionSentinel:
    """Unit tests for the sentinel helper functions in session_start_core."""

    def test_read_absent_sentinel_returns_none(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_start_core import read_session_sentinel

        result = read_session_sentinel(tmp_path)
        assert result is None

    def test_write_then_read_returns_age(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_start_core import read_session_sentinel, write_session_sentinel

        write_session_sentinel(tmp_path)
        age = read_session_sentinel(tmp_path)
        assert age is not None
        assert 0 <= age < 5  # written moments ago

    def test_stale_sentinel_returns_none(self, tmp_path: Path) -> None:
        import os

        from tapps_mcp.tools.session_start_core import SENTINEL_FILENAME, read_session_sentinel

        sentinel = tmp_path / ".tapps-mcp" / SENTINEL_FILENAME
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.touch()
        # Back-date mtime by 2 hours to make it stale.
        stale_time = sentinel.stat().st_mtime - 7200
        os.utime(sentinel, (stale_time, stale_time))

        result = read_session_sentinel(tmp_path, ttl_s=3600)
        assert result is None

    def test_sentinel_age_within_custom_ttl(self, tmp_path: Path) -> None:
        import os

        from tapps_mcp.tools.session_start_core import SENTINEL_FILENAME, read_session_sentinel

        sentinel = tmp_path / ".tapps-mcp" / SENTINEL_FILENAME
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.touch()
        # Back-date by 30 minutes — within default 1 h TTL but beyond a 10 s TTL.
        past_time = sentinel.stat().st_mtime - 1800
        os.utime(sentinel, (past_time, past_time))

        assert read_session_sentinel(tmp_path, ttl_s=3600) is not None  # within 1 h
        assert read_session_sentinel(tmp_path, ttl_s=10) is None  # beyond 10 s

    def test_write_sentinel_creates_directory(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.session_start_core import SENTINEL_FILENAME, write_session_sentinel

        write_session_sentinel(tmp_path)
        assert (tmp_path / ".tapps-mcp" / SENTINEL_FILENAME).exists()

    def test_write_sentinel_touch_updates_mtime(self, tmp_path: Path) -> None:
        import os
        import time

        from tapps_mcp.tools.session_start_core import SENTINEL_FILENAME, write_session_sentinel

        write_session_sentinel(tmp_path)
        sentinel = tmp_path / ".tapps-mcp" / SENTINEL_FILENAME
        old_mtime = sentinel.stat().st_mtime
        # Back-date to simulate a stale sentinel.
        os.utime(sentinel, (old_mtime - 7200, old_mtime - 7200))

        time.sleep(0.01)
        write_session_sentinel(tmp_path)
        new_mtime = sentinel.stat().st_mtime
        assert new_mtime > old_mtime - 7200  # mtime was updated


class TestSessionStartSentinelIntegration:
    """TAP-1928: integration tests for the sentinel short-circuit in tapps_session_start.

    Tests that the second call in a fresh MCP process (in-memory cache cleared)
    returns ``cached: true`` + ``sentinel_age_s`` when the sentinel file is fresh.
    """

    @pytest.mark.asyncio
    async def test_sentinel_hit_returns_cached_minimal_response(self, tmp_path: Path) -> None:
        """After full bootstrap, clearing the in-memory cache and re-calling
        hits the file sentinel and returns the minimal cached response."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start
        from tapps_mcp.tools.session_start_core import write_session_sentinel

        # Pre-write the sentinel as if a prior primary-agent bootstrap ran.
        write_session_sentinel(tmp_path)

        _reset_session_start_cache()
        CallTracker.reset()

        # Patch load_settings so project_root resolves to tmp_path.
        class _FakeSettings:
            project_root = tmp_path
            memory: object = type("M", (), {"enabled": False})()

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_FakeSettings(),
        ):
            resp = await tapps_session_start()

        assert resp["success"] is True
        assert resp["data"]["cached"] is True
        assert "sentinel_age_s" in resp["data"]
        assert resp["data"]["sentinel_age_s"] >= 0

    @pytest.mark.asyncio
    async def test_force_bypasses_sentinel(self, tmp_path: Path) -> None:
        """force=True skips the sentinel and runs the full bootstrap."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start
        from tapps_mcp.tools.session_start_core import write_session_sentinel

        write_session_sentinel(tmp_path)
        _reset_session_start_cache()
        CallTracker.reset()

        # With force=True the sentinel must be ignored — full bootstrap runs.
        resp = await tapps_session_start(force=True)
        assert resp["success"] is True
        assert resp["data"].get("sentinel_age_s") is None  # sentinel path not taken

    @pytest.mark.asyncio
    async def test_absent_sentinel_runs_full_bootstrap(self, tmp_path: Path) -> None:
        """When no sentinel file exists, the full bootstrap runs normally."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        _reset_session_start_cache()
        CallTracker.reset()

        class _FakeSettings:
            project_root = tmp_path
            memory: object = type("M", (), {"enabled": False})()

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_FakeSettings(),
        ):
            # No sentinel written — should run full bootstrap (no sentinel_age_s).
            # We can't intercept collect_session_start_phases without a deep mock,
            # so we just verify the sentinel-cached path was NOT taken.
            # The response will either succeed or fail depending on the environment;
            # what matters is that sentinel_age_s is absent.
            resp = await tapps_session_start()

        assert resp["data"].get("sentinel_age_s") is None
