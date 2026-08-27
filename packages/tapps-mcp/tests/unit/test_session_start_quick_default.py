"""TAP-6434: ``tapps_session_start`` defaults to the compact payload.

The full diagnostic bootstrap was the default, so every routine session start
shipped ~12 kB of brain-health / memory / install-drift / call-graph output the
agent never asked for (~4,463 calls / 30 d on the fleet). Those diagnostics also
live in ``tapps_doctor``.  The default is now ``quick=True``; ``quick=False``
still returns the full payload, unchanged.

Covered here:

- the signature default and the shape of the payload it produces (VAL-10);
- the byte ceiling on the default payload;
- that ``quick=False`` still carries every diagnostics-only block;
- ``recommended_next`` no longer nudges the caller to re-run without ``quick``;
- the two session-lifecycle side effects the compact path had to take over
  (compaction-rehydration marker, persisted session-start ISO) and the one it
  must NOT take over (the TAP-1928 sentinel).
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.server_pipeline_tools import _reset_session_start_cache
from tapps_mcp.tools.checklist import CallTracker

# Diagnostics-only blocks: assembled by the full bootstrap, absent from the
# compact payload, and all available from ``tapps_doctor``.
DIAGNOSTIC_ONLY_FIELDS = (
    "diagnostics",
    "memory_status",
    "brain_bridge_health",
    "timings",
    "call_graph",
    "search_first",
    "usage_gaps",
    "pipeline",
    "quick_start",
    "critical_rules",
)

# Acceptance 4: ceiling for the payload a no-argument call returns.
DEFAULT_PAYLOAD_BYTE_CEILING = 4_000


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    _reset_session_start_cache()
    CallTracker.reset()


class _QuickSettings:
    """Minimal settings stand-in covering what the compact path reads."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.quality_preset = "standard"
        self.log_level = "INFO"
        self.memory = type("_Memory", (), {"enabled": False})()


@pytest.mark.usefixtures("no_session_sentinel")
class TestQuickIsTheDefault:
    """Acceptance 1, 3 and 4."""

    def test_signature_default_is_quick(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        assert inspect.signature(tapps_session_start).parameters["quick"].default is True

    @pytest.mark.asyncio
    async def test_no_argument_call_returns_the_compact_payload(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()

        assert result["success"] is True
        data = result["data"]
        assert data["quick"] is True
        for field in DIAGNOSTIC_ONLY_FIELDS:
            assert field not in data, f"{field} leaked into the compact default payload"
        # The compact payload is still a usable bootstrap.
        assert data["server"]["name"] == "TappsMCP"
        assert data["installed_checkers"]
        assert data["configuration"]["project_root"]

    @pytest.mark.asyncio
    async def test_default_payload_is_under_the_byte_ceiling(self) -> None:
        """VAL-10: the whole point of the flip is response size."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        size = len(json.dumps(result, default=str))

        assert size < DEFAULT_PAYLOAD_BYTE_CEILING, (
            f"default tapps_session_start payload is {size}B, "
            f"ceiling is {DEFAULT_PAYLOAD_BYTE_CEILING}B"
        )

    @pytest.mark.asyncio
    async def test_default_payload_is_far_smaller_than_the_full_one(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        default_size = len(json.dumps(await tapps_session_start(force=True), default=str))
        _reset_session_start_cache()
        full_size = len(json.dumps(await tapps_session_start(quick=False, force=True), default=str))

        assert default_size < full_size

    @pytest.mark.asyncio
    async def test_recommended_next_does_not_nudge_a_rerun(self) -> None:
        """Acceptance 3: the old copy told the caller to call again without quick."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        recommended = (await tapps_session_start())["data"]["recommended_next"]

        assert "without quick" not in recommended
        assert "quick=True" not in recommended
        assert "tapps_doctor" in recommended


@pytest.mark.usefixtures("no_session_sentinel")
class TestExplicitFullStillReachable:
    """Acceptance 2 — the diagnostics did not move, they became opt-in."""

    @pytest.mark.asyncio
    async def test_quick_false_returns_the_diagnostic_blocks(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        data = (await tapps_session_start(quick=False))["data"]

        assert data.get("quick") is not True
        for field in DIAGNOSTIC_ONLY_FIELDS:
            assert field in data, f"{field} missing from the explicit full payload"
        assert "install_drift" in data["diagnostics"]

    @pytest.mark.asyncio
    async def test_default_and_full_are_cached_independently(self) -> None:
        """The memoization key still carries the quick flag (TAP-1379)."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        assert (await tapps_session_start())["data"].get("cached") is not True
        assert (await tapps_session_start(quick=False))["data"].get("cached") is not True
        assert (await tapps_session_start())["data"].get("cached") is True
        assert (await tapps_session_start(quick=False))["data"].get("cached") is True


class TestLifecycleUnchangedByTheFlip:
    """The flip is a payload-size change, not a session-lifecycle change."""

    @pytest.mark.asyncio
    async def test_default_call_does_not_write_the_session_sentinel(
        self, tmp_path: Path
    ) -> None:
        """TAP-1928's sentinel means "a FULL bootstrap ran recently".

        Writing it from the compact path would short-circuit a later
        ``quick=False`` call into the near-empty sentinel response.
        """
        from tapps_mcp.server_pipeline_tools import tapps_session_start
        from tapps_mcp.tools.session_start_core import SENTINEL_FILENAME

        sentinel = tmp_path / ".tapps-mcp" / SENTINEL_FILENAME
        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_QuickSettings(tmp_path),
        ):
            await tapps_session_start()

        assert not sentinel.exists()

    @pytest.mark.asyncio
    async def test_default_call_persists_the_session_start_iso(self, tmp_path: Path) -> None:
        """``tapps_session_end`` scopes flywheel_process with this file."""
        from tapps_mcp.server_pipeline_tools import tapps_session_start
        from tapps_mcp.tools.session_end_helpers import read_persisted_session_start_iso

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_QuickSettings(tmp_path),
        ):
            await tapps_session_start()

        assert read_persisted_session_start_iso(tmp_path).startswith("20")

    @pytest.mark.asyncio
    async def test_default_call_consumes_the_compaction_marker(self, tmp_path: Path) -> None:
        """/tapps-continue-session reads ``compaction_rehydration`` from a
        no-argument call, and the marker is consumed exactly once."""
        from tapps_mcp.memory.compact_index import COMPACTION_MARKER_FILENAME
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        marker = tmp_path / ".tapps-mcp" / COMPACTION_MARKER_FILENAME
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "session_id": "sess-6434",
                    "compacted_at": 1.0,
                    "indexed_in_brain": False,
                }
            ),
            encoding="utf-8",
        )

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_QuickSettings(tmp_path),
        ):
            data: dict[str, Any] = (await tapps_session_start())["data"]

        rehydration = data["compaction_rehydration"]
        assert rehydration["session_id"] == "sess-6434"
        assert not marker.exists(), "marker must be consumed so it does not re-surface"

    @pytest.mark.asyncio
    async def test_default_call_omits_rehydration_when_no_marker(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings",
            return_value=_QuickSettings(tmp_path),
        ):
            data = (await tapps_session_start())["data"]

        assert "compaction_rehydration" not in data
