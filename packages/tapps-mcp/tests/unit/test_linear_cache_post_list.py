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

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tapps_core.config.settings import TappsMCPSettings
from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_CACHE_GATE_HOOKS_CONFIG,
    LINEAR_CACHE_GATE_SCRIPTS,
)
from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks
from tapps_mcp.server_linear_tools import (
    _resolve_cache_key,
    tapps_linear_snapshot_get,
)


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
            "tool_response": {"issues": [{"identifier": "X-1", "title": "keyed"}]},
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


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only behavioral tests")
class TestPostListEmptyCachePoisoning:
    """TAP-5901: the hook must never write a falsely-empty issue list.

    A miss costs one API call; a poisoned hit makes the agent report "no open
    issues" for a project with 160 of them, and every downstream decision built
    on that read is wrong.
    """

    def _setup(self, tmp_path: Path) -> Path:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_cache_gate="warn")
        return tmp_path / ".claude" / "hooks"

    def _run(self, script: Path, stdin: str, *, cwd: Path) -> int:
        proc = subprocess.run(
            ["/usr/bin/env", "bash", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)},
            cwd=str(cwd),
            timeout=10,
        )
        return proc.returncode

    @staticmethod
    def _cache_files(tmp_path: Path) -> list[Path]:
        return list((tmp_path / ".tapps-mcp-cache" / "linear-snapshots").glob("*.json"))

    def test_content_array_envelope_yields_the_real_issue_list(self, tmp_path: Path) -> None:
        """The MCP content-array envelope hides issues inside a JSON string.

        Live repro (2026-08-13, nlt-orchestrator): a 160-issue response cached
        as ``{"issues": []}`` because ``_find_issues`` walked dicts and lists
        but never parsed the nested ``text`` payload.
        """
        hooks = self._setup(tmp_path)
        inner = json.dumps(
            {"issues": [{"id": f"TAP-{n}", "title": f"issue {n}"} for n in range(160)]}
        )
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {
                "team": "TappsCodingAgents",
                "project": "Web-Store-DNA",
                "includeArchived": False,
                "limit": 250,
                "fields": ["id", "title", "status", "statusType"],
            },
            "tool_response": {"content": [{"type": "text", "text": inner}]},
        }
        assert (
            self._run(hooks / "tapps-post-linear-list.sh", json.dumps(payload), cwd=tmp_path) == 0
        )

        files = self._cache_files(tmp_path)
        assert len(files) == 1
        entry = json.loads(files[0].read_text(encoding="utf-8"))
        assert len(entry["issues"]) == 160
        assert entry["issues"][0]["id"] == "TAP-0"

    def test_empty_result_with_state_omitted_writes_nothing(self, tmp_path: Path) -> None:
        """The ``linear-read`` skill omits ``state``; that must not poison ``open``."""
        hooks = self._setup(tmp_path)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {"team": "TappsCodingAgents", "project": "Web-Store-DNA"},
            "tool_response": {"issues": []},
        }
        assert (
            self._run(hooks / "tapps-post-linear-list.sh", json.dumps(payload), cwd=tmp_path) == 0
        )
        assert self._cache_files(tmp_path) == []

    def test_empty_result_with_real_state_writes_nothing(self, tmp_path: Path) -> None:
        """A valid state does not license an empty write either."""
        hooks = self._setup(tmp_path)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {"team": "TAP", "project": "P", "state": "completed"},
            "tool_response": {"issues": []},
        }
        assert (
            self._run(hooks / "tapps-post-linear-list.sh", json.dumps(payload), cwd=tmp_path) == 0
        )
        assert self._cache_files(tmp_path) == []

    def test_unparseable_response_writes_nothing(self, tmp_path: Path) -> None:
        """An envelope the parser cannot read must fail open, not cache zero."""
        hooks = self._setup(tmp_path)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {"team": "TAP", "project": "P"},
            "tool_response": {"content": [{"type": "text", "text": "not json at all"}]},
        }
        assert (
            self._run(hooks / "tapps-post-linear-list.sh", json.dumps(payload), cwd=tmp_path) == 0
        )
        assert self._cache_files(tmp_path) == []

    def test_content_array_envelope_with_no_issues_writes_nothing(self, tmp_path: Path) -> None:
        """A genuinely empty content-array response also fails open."""
        hooks = self._setup(tmp_path)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {"team": "TAP", "project": "P"},
            "tool_response": {"content": [{"type": "text", "text": json.dumps({"issues": []})}]},
        }
        assert (
            self._run(hooks / "tapps-post-linear-list.sh", json.dumps(payload), cwd=tmp_path) == 0
        )
        assert self._cache_files(tmp_path) == []

    def test_top_level_json_string_response_still_parses(self, tmp_path: Path) -> None:
        """The pre-existing whole-response-is-a-string path must keep working."""
        hooks = self._setup(tmp_path)
        payload = {
            "tool_name": "mcp__plugin_linear_linear__list_issues",
            "tool_input": {"team": "TAP", "project": "P", "state": "started"},
            "tool_response": json.dumps({"issues": [{"id": "TAP-9", "title": "x"}]}),
        }
        assert (
            self._run(hooks / "tapps-post-linear-list.sh", json.dumps(payload), cwd=tmp_path) == 0
        )
        entry = json.loads(self._cache_files(tmp_path)[0].read_text(encoding="utf-8"))
        assert [i["id"] for i in entry["issues"]] == ["TAP-9"]


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only behavioral tests")
class TestPostListContentsGuard:
    """TAP-6581: the write guard must test the CONTENTS, not just the container.

    The pre-existing poisoning guard refused an empty issue LIST but happily
    stored a list of empty ROWS. A ``list_issues(fields=["id"])`` response
    therefore cached 36 one-field rows under the canonical open-bucket key,
    which ``snapshot_get`` then served for the full 30-minute TTL labelled
    ``projection: "full"``. Every refusal here must also be VISIBLE — the old
    bare ``sys.exit(0)`` made a refusal indistinguishable from a write.
    """

    def _setup(self, tmp_path: Path) -> Path:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_cache_gate="warn")
        return tmp_path / ".claude" / "hooks"

    def _run(self, script: Path, stdin: str, cwd: Path) -> tuple[int, str]:
        proc = subprocess.run(
            ["/usr/bin/env", "bash", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)},
            cwd=str(cwd),
            timeout=10,
        )
        return proc.returncode, proc.stderr

    @staticmethod
    def _cache_files(tmp_path: Path) -> list[Path]:
        return list((tmp_path / ".tapps-mcp-cache" / "linear-snapshots").glob("*.json"))

    @staticmethod
    def _refusals(tmp_path: Path) -> list[dict[str, Any]]:
        log = tmp_path / ".tapps-mcp" / ".linear-cache-write-refusals.jsonl"
        if not log.exists():
            return []
        return [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln]

    @staticmethod
    def _payload(issues: list[dict[str, Any]]) -> str:
        return json.dumps(
            {
                "tool_name": "mcp__plugin_linear_linear__list_issues",
                "tool_input": {"team": "TAP", "project": "P", "limit": 50},
                "tool_response": {"issues": issues},
            }
        )

    def test_id_only_rows_are_refused_loudly(self, tmp_path: Path) -> None:
        """The live repro: ``fields=["id"]`` rows must never reach the cache."""
        hooks = self._setup(tmp_path)
        rc, stderr = self._run(
            hooks / "tapps-post-linear-list.sh",
            self._payload([{"id": f"uuid-{n}"} for n in range(36)]),
            cwd=tmp_path,
        )
        assert rc == 0, "PostToolUse must stay fail-open"
        assert self._cache_files(tmp_path) == []
        assert "tapps-post-linear-list: refused cache write" in stderr
        assert "reason=rows_below_compact_floor" in stderr
        assert [r["reason"] for r in self._refusals(tmp_path)] == ["rows_below_compact_floor"]

    def test_row_missing_title_is_refused(self, tmp_path: Path) -> None:
        """Identity alone is not enough — an untitled row is unreadable."""
        hooks = self._setup(tmp_path)
        _, stderr = self._run(
            hooks / "tapps-post-linear-list.sh",
            self._payload([{"id": "u1", "identifier": "TAP-1", "priority": 2}]),
            cwd=tmp_path,
        )
        assert self._cache_files(tmp_path) == []
        assert "reason=rows_below_compact_floor" in stderr

    def test_one_bad_row_refuses_the_whole_write(self, tmp_path: Path) -> None:
        """A partially-degraded payload is still a payload the reader cannot trust."""
        hooks = self._setup(tmp_path)
        _, stderr = self._run(
            hooks / "tapps-post-linear-list.sh",
            self._payload([{"id": "u1", "title": "good"}, {"id": "u2"}]),
            cwd=tmp_path,
        )
        assert self._cache_files(tmp_path) == []
        assert "reason=rows_below_compact_floor" in stderr

    def test_compact_rows_are_still_written(self, tmp_path: Path) -> None:
        """Negative path: the floor must not reject legitimate triage rows."""
        hooks = self._setup(tmp_path)
        rc, stderr = self._run(
            hooks / "tapps-post-linear-list.sh",
            self._payload([{"id": "u1", "identifier": "TAP-1", "title": "alpha"}]),
            cwd=tmp_path,
        )
        assert rc == 0
        assert "refused cache write" not in stderr
        entry = json.loads(self._cache_files(tmp_path)[0].read_text(encoding="utf-8"))
        assert [i["identifier"] for i in entry["issues"]] == ["TAP-1"]

    def test_empty_list_refusal_is_now_visible(self, tmp_path: Path) -> None:
        """The container-level guard kept its verdict but lost its silence."""
        hooks = self._setup(tmp_path)
        _, stderr = self._run(hooks / "tapps-post-linear-list.sh", self._payload([]), cwd=tmp_path)
        assert self._cache_files(tmp_path) == []
        assert "reason=empty_issue_list" in stderr
        assert [r["reason"] for r in self._refusals(tmp_path)] == ["empty_issue_list"]

    def test_narrow_read_cannot_degrade_a_richer_entry(self, tmp_path: Path) -> None:
        """Acceptance 4: a narrow ``fields=`` read must not overwrite a rich entry."""
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-post-linear-list.sh"
        rich = [
            {"id": "u1", "identifier": "TAP-1", "title": "alpha", "priority": 2},
            {"id": "u2", "identifier": "TAP-2", "title": "beta", "priority": 3},
        ]
        self._run(script, self._payload(rich), cwd=tmp_path)
        before = json.loads(self._cache_files(tmp_path)[0].read_text(encoding="utf-8"))

        narrow = [{"id": "u1", "title": "alpha"}, {"id": "u2", "title": "beta"}]
        _, stderr = self._run(script, self._payload(narrow), cwd=tmp_path)

        after = json.loads(self._cache_files(tmp_path)[0].read_text(encoding="utf-8"))
        assert after["issues"] == before["issues"], "narrow read overwrote the richer entry"
        assert "reason=would_degrade_cached_entry" in stderr

    def test_equally_rich_refresh_still_writes(self, tmp_path: Path) -> None:
        """Negative path: the no-degrade guard must not freeze the cache."""
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-post-linear-list.sh"
        self._run(
            script,
            self._payload([{"id": "u1", "identifier": "TAP-1", "title": "alpha"}]),
            cwd=tmp_path,
        )
        _, stderr = self._run(
            script,
            self._payload(
                [
                    {"id": "u1", "identifier": "TAP-1", "title": "alpha"},
                    {"id": "u2", "identifier": "TAP-2", "title": "beta"},
                ]
            ),
            cwd=tmp_path,
        )
        assert "refused cache write" not in stderr
        entry = json.loads(self._cache_files(tmp_path)[0].read_text(encoding="utf-8"))
        assert [i["identifier"] for i in entry["issues"]] == ["TAP-1", "TAP-2"]


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only behavioral tests")
class TestPostListToSnapshotGetHonesty:
    """TAP-6581 acceptance 5: the 30-min open-bucket TTL cannot serve a degraded
    entry left by an unrelated narrow read in the same session.

    Two independent layers, both asserted here: the hook never writes such an
    entry, and the reader refuses to serve one that is already on disk (an
    entry written by a pre-fix hook, or by a manual ``snapshot_put``).
    """

    def _settings(self, tmp_path: Path) -> Any:
        class _Stub:
            project_root = tmp_path
            linear_cache_ttl_open_seconds = 1800
            linear_cache_ttl_closed_seconds = 3600

        return _Stub()

    def test_hook_refusal_leaves_nothing_for_the_ttl_to_serve(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_cache_gate="warn")
        subprocess.run(
            [
                "/usr/bin/env",
                "bash",
                str(tmp_path / ".claude" / "hooks" / "tapps-post-linear-list.sh"),
            ],
            input=json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__list_issues",
                    "tool_input": {"team": "TAP", "project": "P"},
                    "tool_response": {"issues": [{"id": f"uuid-{n}"} for n in range(36)]},
                }
            ),
            capture_output=True,
            text=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=str(tmp_path),
            timeout=10,
        )
        with patch(
            "tapps_mcp.server_linear_tools.load_settings",
            return_value=self._settings(tmp_path),
        ):
            got = asyncio.run(tapps_linear_snapshot_get(team="TAP", project="P", state="open"))
        assert got["data"]["cached"] is False
        assert got["data"]["miss_reason"] == "not_cached"

    def test_preexisting_degraded_entry_misses_inside_its_ttl(self, tmp_path: Path) -> None:
        """A live-TTL entry written before this fix must still not be served."""
        cache_dir = tmp_path / ".tapps-mcp-cache" / "linear-snapshots"
        cache_dir.mkdir(parents=True)
        now = time.time()
        key = _resolve_cache_key("TAP", "P", "open", "", 50)
        (cache_dir / f"{key}.json").write_text(
            json.dumps(
                {
                    "issues": [{"id": f"uuid-{n}"} for n in range(36)],
                    "cached_at": now,
                    "expires_at": now + 1800,
                    "auto_populated": True,
                    "limit": 50,
                }
            ),
            encoding="utf-8",
        )
        with patch(
            "tapps_mcp.server_linear_tools.load_settings",
            return_value=self._settings(tmp_path),
        ):
            got = asyncio.run(tapps_linear_snapshot_get(team="TAP", project="P", state="open"))
        assert got["data"]["cached"] is False
        assert got["data"]["miss_reason"] == "degraded_rows"
        assert "projection" not in got["data"]


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
