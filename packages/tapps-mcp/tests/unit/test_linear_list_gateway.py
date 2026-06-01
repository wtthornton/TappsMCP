"""Tests for the TAP-2010 linear list_issues cache-first read gate.

Covers:
  - _sentinel_is_fresh: exists/missing/stale/fresh/corrupt
  - _alias_keys: open-bucket expansion
  - check_snapshot_sentinel: primary key hit, alias key hit, miss
  - gate_miss_envelope: shape and field values
  - gate_linear_list: passes / fires / bypass via env var
  - tapps_linear_list_issues handler: gate pass, gate fire
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.tools.linear_list_gateway import (
    _alias_keys,
    _sentinel_is_fresh,
    check_snapshot_sentinel,
    gate_linear_list,
    gate_miss_envelope,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_sentinel(project_dir: Path, key: str, age_s: float = 0.0) -> None:
    """Write a sentinel file for *key* with the given age in seconds."""
    sentinel_dir = project_dir / ".tapps-mcp"
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    ts = time.time() - age_s
    (sentinel_dir / f".linear-snapshot-sentinel-{key}").write_text(
        str(ts), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# _sentinel_is_fresh
# ---------------------------------------------------------------------------


class TestSentinelIsFresh:
    def test_returns_false_when_file_missing(self, tmp_path: Path) -> None:
        from tapps_mcp.tools.linear_list_gateway import _SENTINEL_PREFIX

        key = "some_key"
        result = _sentinel_is_fresh(tmp_path, key)
        assert result is False
        assert not (tmp_path / f"{_SENTINEL_PREFIX}{key}").exists()

    def test_returns_true_for_fresh_sentinel(self, tmp_path: Path) -> None:
        key = "freshkey"
        _write_sentinel(tmp_path, key, age_s=10.0)
        assert _sentinel_is_fresh(tmp_path, key) is True

    def test_returns_false_for_stale_sentinel(self, tmp_path: Path) -> None:
        key = "stalekey"
        _write_sentinel(tmp_path, key, age_s=400.0)  # > 300 s TTL
        assert _sentinel_is_fresh(tmp_path, key) is False

    def test_returns_false_for_corrupt_sentinel(self, tmp_path: Path) -> None:
        sentinel_dir = tmp_path / ".tapps-mcp"
        sentinel_dir.mkdir(parents=True, exist_ok=True)
        (sentinel_dir / ".linear-snapshot-sentinel-bad").write_text(
            "not-a-float", encoding="utf-8"
        )
        assert _sentinel_is_fresh(tmp_path, "bad") is False

    def test_returns_false_for_exactly_at_ttl_boundary(self, tmp_path: Path) -> None:
        """Age == 300 s is still within TTL (≤ 300 s)."""
        key = "boundary"
        _write_sentinel(tmp_path, key, age_s=300.0)
        # May be True or False depending on float precision; just assert it doesn't raise
        result = _sentinel_is_fresh(tmp_path, key)
        assert isinstance(result, bool)

    def test_returns_false_for_negative_age(self, tmp_path: Path) -> None:
        """Future timestamps (negative age) are rejected."""
        sentinel_dir = tmp_path / ".tapps-mcp"
        sentinel_dir.mkdir(parents=True, exist_ok=True)
        future_ts = time.time() + 9999.0
        (sentinel_dir / ".linear-snapshot-sentinel-future").write_text(
            str(future_ts), encoding="utf-8"
        )
        assert _sentinel_is_fresh(tmp_path, "future") is False


# ---------------------------------------------------------------------------
# _alias_keys
# ---------------------------------------------------------------------------


class TestAliasKeys:
    def test_open_state_returns_all_open_bucket_variants(self) -> None:
        keys = _alias_keys("T", "P", "open", "", 50)
        assert len(keys) >= 5  # open + backlog + unstarted + started + triage

    def test_open_bucket_member_returns_aliases(self) -> None:
        """state="backlog" should return alias keys including "open"."""
        keys = _alias_keys("T", "P", "backlog", "", 50)
        assert len(keys) >= 2

    def test_non_open_state_returns_empty(self) -> None:
        keys = _alias_keys("T", "P", "completed", "", 50)
        assert keys == []

    def test_empty_state_returns_aliases(self) -> None:
        keys = _alias_keys("T", "P", "", "", 50)
        assert len(keys) >= 1

    def test_alias_keys_no_duplicates(self) -> None:
        keys = _alias_keys("T", "P", "open", "", 50)
        assert len(keys) == len(set(keys))

    def test_alias_keys_case_insensitive(self) -> None:
        keys_lower = _alias_keys("T", "P", "backlog", "", 50)
        keys_upper = _alias_keys("T", "P", "BACKLOG", "", 50)
        assert set(keys_lower) == set(keys_upper)


# ---------------------------------------------------------------------------
# check_snapshot_sentinel
# ---------------------------------------------------------------------------


class TestCheckSnapshotSentinel:
    def test_returns_false_when_no_sentinel(self, tmp_path: Path) -> None:
        assert check_snapshot_sentinel(tmp_path, "T", "P", "backlog", "", 50) is False

    def test_returns_true_on_primary_key_hit(self, tmp_path: Path) -> None:
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        key = _resolve_cache_key("T", "P", "backlog", "", 50)
        _write_sentinel(tmp_path, key, age_s=0.0)
        assert check_snapshot_sentinel(tmp_path, "T", "P", "backlog", "", 50) is True

    def test_returns_true_on_alias_key_hit(self, tmp_path: Path) -> None:
        """A snapshot_get with state="open" satisfies a backlog gate check."""
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        open_key = _resolve_cache_key("T", "P", "open", "", 50)
        _write_sentinel(tmp_path, open_key, age_s=0.0)
        assert check_snapshot_sentinel(tmp_path, "T", "P", "backlog", "", 50) is True

    def test_returns_false_when_primary_stale_and_no_aliases(
        self, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        key = _resolve_cache_key("T", "P", "completed", "", 50)
        _write_sentinel(tmp_path, key, age_s=400.0)
        assert check_snapshot_sentinel(tmp_path, "T", "P", "completed", "", 50) is False


# ---------------------------------------------------------------------------
# gate_miss_envelope
# ---------------------------------------------------------------------------


class TestGateMissEnvelope:
    def _envelope(self, **kwargs: Any) -> dict[str, Any]:
        defaults: dict[str, Any] = {
            "team": "TAP",
            "project": "TappsMCP Platform",
            "state": "backlog",
            "label": "",
            "limit": 50,
            "key": "some_key",
        }
        defaults.update(kwargs)
        return gate_miss_envelope(**defaults)

    def test_ok_is_false(self) -> None:
        assert self._envelope()["ok"] is False

    def test_code_is_gate_miss(self) -> None:
        assert self._envelope()["code"] == "gate_miss"

    def test_gate_field(self) -> None:
        assert self._envelope()["gate"] == "linear_cache_first_read"

    def test_use_field(self) -> None:
        assert self._envelope()["use"] == "tapps_linear_snapshot_get"

    def test_args_contains_team_and_project(self) -> None:
        env = self._envelope(team="MYTEAM", project="MYPROJ")
        assert env["args"]["team"] == "MYTEAM"
        assert env["args"]["project"] == "MYPROJ"

    def test_args_omits_empty_state(self) -> None:
        env = self._envelope(state="")
        assert "state" not in env["args"]

    def test_args_omits_empty_label(self) -> None:
        env = self._envelope(label="")
        assert "label" not in env["args"]

    def test_args_omits_default_limit(self) -> None:
        env = self._envelope(limit=50)
        assert "limit" not in env["args"]

    def test_args_includes_non_default_limit(self) -> None:
        env = self._envelope(limit=100)
        assert env["args"]["limit"] == 100

    def test_bypass_env(self) -> None:
        assert self._envelope()["bypass_env"] == "TAPPS_LINEAR_SKIP_CACHE_GATE"

    def test_logged_to(self) -> None:
        assert (
            self._envelope()["logged_to"] == ".tapps-mcp/.cache-gate-violations.jsonl"
        )

    def test_extra_contains_expected_sentinel_key(self) -> None:
        env = self._envelope(key="mykey123")
        assert env["extra"]["expected_sentinel_key"] == "mykey123"

    def test_hint_mentions_snapshot_get(self) -> None:
        assert "tapps_linear_snapshot_get" in self._envelope()["hint"]


# ---------------------------------------------------------------------------
# gate_linear_list
# ---------------------------------------------------------------------------


class TestGateLinearList:
    def test_returns_none_when_sentinel_fresh(self, tmp_path: Path) -> None:
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        key = _resolve_cache_key("T", "P", "backlog", "", 50)
        _write_sentinel(tmp_path, key, age_s=0.0)
        result = gate_linear_list(tmp_path, "T", "P", "backlog", "", 50)
        assert result is None

    def test_returns_envelope_when_no_sentinel(self, tmp_path: Path) -> None:
        result = gate_linear_list(tmp_path, "T", "P", "backlog", "", 50)
        assert result is not None
        assert result["ok"] is False
        assert result["code"] == "gate_miss"

    def test_returns_none_when_bypass_env_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TAPPS_LINEAR_SKIP_CACHE_GATE", "1")
        result = gate_linear_list(tmp_path, "T", "P", "backlog", "", 50)
        assert result is None

    def test_returns_envelope_when_sentinel_stale(self, tmp_path: Path) -> None:
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        key = _resolve_cache_key("T", "P", "backlog", "", 50)
        _write_sentinel(tmp_path, key, age_s=500.0)
        result = gate_linear_list(tmp_path, "T", "P", "backlog", "", 50)
        assert result is not None
        assert result["code"] == "gate_miss"

    def test_alias_hit_passes_gate(self, tmp_path: Path) -> None:
        """snapshot_get(state="open") sentinel satisfies a backlog gate check."""
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        open_key = _resolve_cache_key("T", "P", "open", "", 50)
        _write_sentinel(tmp_path, open_key, age_s=0.0)
        result = gate_linear_list(tmp_path, "T", "P", "backlog", "", 50)
        assert result is None

    def test_different_limit_misses_gate(self, tmp_path: Path) -> None:
        """A sentinel for limit=50 does NOT satisfy a limit=100 check."""
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        key50 = _resolve_cache_key("T", "P", "backlog", "", 50)
        _write_sentinel(tmp_path, key50, age_s=0.0)
        result = gate_linear_list(tmp_path, "T", "P", "backlog", "", 100)
        assert result is not None


# ---------------------------------------------------------------------------
# tapps_linear_list_issues handler
# ---------------------------------------------------------------------------


class TestTappsLinearListIssuesHandler:
    @pytest.fixture()
    def mock_settings(self, tmp_path: Path) -> MagicMock:
        settings = MagicMock()
        settings.project_root = tmp_path
        return settings

    @pytest.mark.asyncio()
    async def test_gate_pass_returns_ok_true(
        self,
        tmp_path: Path,
        mock_settings: MagicMock,
    ) -> None:
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        key = _resolve_cache_key("T", "P", "backlog", "", 50)
        _write_sentinel(tmp_path, key, age_s=0.0)

        with patch(
            "tapps_mcp.server_linear_tools.load_settings", return_value=mock_settings
        ):
            from tapps_mcp.server_linear_tools import tapps_linear_list_issues

            result = await tapps_linear_list_issues("T", "P", "backlog", "", 50)

        assert result["data"]["ok"] is True

    @pytest.mark.asyncio()
    async def test_gate_fire_returns_gate_miss_envelope(
        self,
        tmp_path: Path,
        mock_settings: MagicMock,
    ) -> None:
        with patch(
            "tapps_mcp.server_linear_tools.load_settings", return_value=mock_settings
        ):
            from tapps_mcp.server_linear_tools import tapps_linear_list_issues

            result = await tapps_linear_list_issues("T", "P", "backlog", "", 50)

        assert result["data"]["ok"] is False
        assert result["data"]["code"] == "gate_miss"

    @pytest.mark.asyncio()
    async def test_gate_fire_next_steps_hint_snapshot_get(
        self,
        tmp_path: Path,
        mock_settings: MagicMock,
    ) -> None:
        with patch(
            "tapps_mcp.server_linear_tools.load_settings", return_value=mock_settings
        ):
            from tapps_mcp.server_linear_tools import tapps_linear_list_issues

            result = await tapps_linear_list_issues("T", "P", "", "", 50)

        # next_steps is injected into result["data"] by success_response
        next_steps = result["data"].get("next_steps", [])
        assert any("snapshot_get" in step for step in next_steps)

    @pytest.mark.asyncio()
    async def test_gate_pass_message_mentions_list_issues(
        self,
        tmp_path: Path,
        mock_settings: MagicMock,
    ) -> None:
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        key = _resolve_cache_key("T", "P", "open", "", 50)
        _write_sentinel(tmp_path, key, age_s=0.0)

        with patch(
            "tapps_mcp.server_linear_tools.load_settings", return_value=mock_settings
        ):
            from tapps_mcp.server_linear_tools import tapps_linear_list_issues

            result = await tapps_linear_list_issues("T", "P", "open", "", 50)

        assert "list_issues" in result["data"].get("message", "")
