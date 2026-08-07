"""Tests for the Linear list_issues PostToolUse auto-populate hook (TAP-1412).

Covers the ``tapps-post-linear-list.sh`` hook that auto-writes the snapshot
cache file from a ``list_issues`` response so the next
``tapps_linear_snapshot_get`` call returns ``cached=true`` without the agent
having to call ``snapshot_put`` manually, plus the VAL-9/VAL-10 contract on
that cache write: partial-slice caching (team-only or project-only reads
still populate the cache), the compact issue shape (heavy fields stripped,
``statusType`` synthesized), and the 30-minute open-bucket TTL staying in
lockstep with the settings default. Also covers hook registration in the
scripts map and PostToolUse matcher list.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_core.config.settings import TappsMCPSettings
from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_CACHE_GATE_HOOKS_CONFIG,
    LINEAR_CACHE_GATE_SCRIPTS,
)
from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only behavioral tests")
class TestPostListAutoPopulate:
    """TAP-1412: the PostToolUse hook on list_issues must auto-write the
    snapshot cache file from the response so the next snapshot_get returns
    cached=true without requiring the agent to call snapshot_put.
    """

    def _setup(self, tmp_path: Path) -> Path:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_cache_gate="warn")
        return tmp_path / ".claude" / "hooks"

    def _run(self, script: Path, stdin: str, *, env: dict[str, str], cwd: Path) -> tuple[int, str]:
        full_env = {**os.environ, **env}
        proc = subprocess.run(
            ["/usr/bin/env", "bash", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            env=full_env,
            cwd=str(cwd),
            timeout=10,
        )
        return proc.returncode, proc.stderr

    def test_auto_populate_writes_cache_file(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {"team": "TAP", "project": "P", "state": "unstarted"},
            "tool_response": {
                "data": {
                    "issues": [
                        {"identifier": "TAP-1", "title": "alpha"},
                        {"identifier": "TAP-2", "title": "beta"},
                    ]
                }
            },
        }
        rc, _ = self._run(
            hooks / "tapps-post-linear-list.sh",
            json.dumps(payload),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        cache_dir = tmp_path / ".tapps-mcp-cache" / "linear-snapshots"
        files = list(cache_dir.glob("*.json"))
        assert len(files) == 1, f"expected 1 cache file, got {[f.name for f in files]}"
        body = json.loads(files[0].read_text(encoding="utf-8"))
        assert body["auto_populated"] is True
        assert len(body["issues"]) == 2
        assert body["issues"][0]["identifier"] == "TAP-1"
        # Sentinel also written so subsequent list_issues passes the gate.
        sentinels = list((tmp_path / ".tapps-mcp").glob(".linear-snapshot-sentinel-*"))
        assert sentinels

    def test_auto_populate_key_matches_snapshot_tool(self, tmp_path: Path) -> None:
        """Cache file written by hook must use the SAME key the server's
        tapps_linear_snapshot_get derives, otherwise the next get misses.
        """
        from tapps_mcp.server_linear_tools import _resolve_cache_key

        hooks = self._setup(tmp_path)
        team, project, state = "TAP", "P", "started"
        expected_key = _resolve_cache_key(team, project, state, "", 50)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {"team": team, "project": project, "state": state},
            "tool_response": {"issues": [{"identifier": "X-1"}]},
        }
        self._run(
            hooks / "tapps-post-linear-list.sh",
            json.dumps(payload),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        cache_file = tmp_path / ".tapps-mcp-cache" / "linear-snapshots" / f"{expected_key}.json"
        assert cache_file.exists(), (
            f"auto-populate key drifted from server-side key derivation: "
            f"expected {expected_key}.json"
        )

    def test_auto_populate_caches_without_both_team_and_project(self, tmp_path: Path) -> None:
        """A partial-slice read must still populate the cache (VAL-9).

        This previously asserted the opposite: the hook exited early unless
        BOTH team and project were present, so a team-only or project-only
        list_issues cached nothing and the gate logged a miss on the follow-up
        read. The reader's ``_cache_key`` falls back to ``'_'`` for an empty
        segment exactly as the writer does, so the key still round-trips.
        """
        hooks = self._setup(tmp_path)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {"team": "TappsCodingAgents", "state": "started"},
            "tool_response": {"issues": [{"id": "TAP-1", "title": "x"}]},
        }
        rc, _ = self._run(
            hooks / "tapps-post-linear-list.sh",
            json.dumps(payload),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        cache_dir = tmp_path / ".tapps-mcp-cache" / "linear-snapshots"
        written = list(cache_dir.glob("*.json"))
        assert written, "team-only read must still write a cache entry"
        # Empty project collapses to the '_' segment the reader also produces.
        assert written[0].name.startswith("TappsCodingAgents___")
        entry = json.loads(written[0].read_text(encoding="utf-8"))
        assert entry["issues"] == [{"id": "TAP-1", "title": "x"}]

    def test_auto_populate_stores_compact_shape(self, tmp_path: Path) -> None:
        """Cached issues carry only the compact field set (VAL-9).

        Mirrors ``server_linear_tools_keys._compact_issue``: heavy fields are
        dropped and ``statusType`` is synthesized from ``state.type`` so a
        50-issue backlog stays under the Read tool's token ceiling.
        """
        hooks = self._setup(tmp_path)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {
                "team": "TappsCodingAgents",
                "project": "TappsMCP Platform",
                "state": "started",
            },
            "tool_response": {
                "issues": [
                    {
                        "id": "abc",
                        "identifier": "TAP-1",
                        "title": "Keep me",
                        "state": {"name": "In Progress", "type": "started"},
                        "priority": 2,
                        "description": "x" * 5000,
                        "comments": [{"body": "y" * 5000}],
                        "history": ["h"] * 100,
                    }
                ]
            },
        }
        rc, _ = self._run(
            hooks / "tapps-post-linear-list.sh",
            json.dumps(payload),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        cache_dir = tmp_path / ".tapps-mcp-cache" / "linear-snapshots"
        entry = json.loads(next(iter(cache_dir.glob("*.json"))).read_text(encoding="utf-8"))
        issue = entry["issues"][0]
        assert issue["identifier"] == "TAP-1"
        assert issue["statusType"] == "started"
        for heavy in ("description", "comments", "history"):
            assert heavy not in issue

    def test_auto_populate_open_ttl_matches_settings_default(self, tmp_path: Path) -> None:
        """Hook TTL must stay in lockstep with the settings default (VAL-10)."""
        hooks = self._setup(tmp_path)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {
                "team": "TappsCodingAgents",
                "project": "TappsMCP Platform",
                "state": "started",
            },
            "tool_response": {"issues": [{"id": "TAP-1", "title": "x"}]},
        }
        rc, _ = self._run(
            hooks / "tapps-post-linear-list.sh",
            json.dumps(payload),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        cache_dir = tmp_path / ".tapps-mcp-cache" / "linear-snapshots"
        entry = json.loads(next(iter(cache_dir.glob("*.json"))).read_text(encoding="utf-8"))
        assert round(entry["expires_at"] - entry["cached_at"]) == 1800
        assert TappsMCPSettings().linear_cache_ttl_open_seconds == 1800


class TestPostListHookRegistration:
    """The auto-populate hook must be wired into both the scripts map and
    the PostToolUse matcher list.
    """

    def test_post_list_script_registered(self) -> None:
        assert "tapps-post-linear-list.sh" in LINEAR_CACHE_GATE_SCRIPTS

    def test_post_list_matcher_registered(self) -> None:
        post = LINEAR_CACHE_GATE_HOOKS_CONFIG["PostToolUse"]
        matchers = [e["matcher"] for e in post]
        assert "mcp__plugin_linear_linear__list_issues" in matchers
