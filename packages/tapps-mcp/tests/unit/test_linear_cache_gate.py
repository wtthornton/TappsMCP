"""Tests for the Linear cache-first read gate (TAP-1224).

Covers the opt-in ``linear_enforce_cache_gate`` mode (off|warn|block) on
``generate_claude_hooks``, mode-baking via the ``__CACHE_GATE_MODE__``
placeholder, the cooperating hook pair (``tapps-post-linear-snapshot-get.sh``
+ ``tapps-pre-linear-list.sh``), and behavioral end-to-end via subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_CACHE_GATE_HOOKS_CONFIG,
    LINEAR_CACHE_GATE_HOOKS_CONFIG_PS,
    LINEAR_CACHE_GATE_POST_SNAPSHOT_SCRIPT,
    LINEAR_CACHE_GATE_POST_SNAPSHOT_SCRIPT_PS,
    LINEAR_CACHE_GATE_PRE_LIST_SCRIPT,
    LINEAR_CACHE_GATE_PRE_LIST_SCRIPT_PS,
    LINEAR_CACHE_GATE_SCRIPTS,
    LINEAR_CACHE_GATE_SCRIPTS_PS,
    render_cache_gate_scripts,
)
from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks


class TestCacheGateConfig:
    """Static checks on the hook config and script templates."""

    def test_pretooluse_matches_list_issues(self) -> None:
        matchers = [e["matcher"] for e in LINEAR_CACHE_GATE_HOOKS_CONFIG["PreToolUse"]]
        assert "mcp__plugin_linear_linear__list_issues" in matchers

    def test_posttooluse_matches_snapshot_get(self) -> None:
        matchers = [e["matcher"] for e in LINEAR_CACHE_GATE_HOOKS_CONFIG["PostToolUse"]]
        assert "mcp__tapps-mcp__tapps_linear_snapshot_get" in matchers

    def test_scripts_map_has_both(self) -> None:
        assert "tapps-pre-linear-list.sh" in LINEAR_CACHE_GATE_SCRIPTS
        assert "tapps-post-linear-snapshot-get.sh" in LINEAR_CACHE_GATE_SCRIPTS

    def test_pre_list_has_mode_placeholder(self) -> None:
        assert "__CACHE_GATE_MODE__" in LINEAR_CACHE_GATE_PRE_LIST_SCRIPT

    def test_pre_list_mentions_bypass_env_var(self) -> None:
        assert "TAPPS_LINEAR_SKIP_CACHE_GATE" in LINEAR_CACHE_GATE_PRE_LIST_SCRIPT

    def test_pre_list_references_linear_standards_rule(self) -> None:
        assert "linear-standards.md" in LINEAR_CACHE_GATE_PRE_LIST_SCRIPT

    def test_post_snapshot_writes_sentinel(self) -> None:
        assert ".linear-snapshot-sentinel-" in LINEAR_CACHE_GATE_POST_SNAPSHOT_SCRIPT

    def test_render_warn_bakes_warn(self) -> None:
        scripts = render_cache_gate_scripts("warn")
        assert 'MODE="warn"' in scripts["tapps-pre-linear-list.sh"]
        assert "__CACHE_GATE_MODE__" not in scripts["tapps-pre-linear-list.sh"]

    def test_render_block_bakes_block(self) -> None:
        scripts = render_cache_gate_scripts("block")
        assert 'MODE="block"' in scripts["tapps-pre-linear-list.sh"]

    def test_render_unknown_mode_falls_back_to_warn(self) -> None:
        scripts = render_cache_gate_scripts("garbage")
        assert 'MODE="warn"' in scripts["tapps-pre-linear-list.sh"]


class TestCacheGateFlagWiring:
    """The ``linear_enforce_cache_gate`` mode plumbs scripts + matchers correctly."""

    def test_off_by_default(self, tmp_path: Path) -> None:
        result = generate_claude_hooks(tmp_path, force_windows=False)
        assert result["linear_enforce_cache_gate"] == "off"
        assert not (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-list.sh").exists()
        assert not (tmp_path / ".claude" / "hooks" / "tapps-post-linear-snapshot-get.sh").exists()

    def test_warn_writes_both_scripts(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_cache_gate="warn")
        assert (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-list.sh").exists()
        assert (tmp_path / ".claude" / "hooks" / "tapps-post-linear-snapshot-get.sh").exists()

    def test_warn_bakes_mode(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_cache_gate="warn")
        body = (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-list.sh").read_text(
            encoding="utf-8"
        )
        assert 'MODE="warn"' in body
        assert "__CACHE_GATE_MODE__" not in body

    def test_block_bakes_mode(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_cache_gate="block")
        body = (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-list.sh").read_text(
            encoding="utf-8"
        )
        assert 'MODE="block"' in body

    def test_warn_adds_matchers_to_settings(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_cache_gate="warn")
        settings = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        pre = [e.get("matcher") for e in settings["hooks"].get("PreToolUse", [])]
        post = [e.get("matcher") for e in settings["hooks"].get("PostToolUse", [])]
        assert "mcp__plugin_linear_linear__list_issues" in pre
        assert "mcp__tapps-mcp__tapps_linear_snapshot_get" in post

    def test_independent_of_save_issue_gate(self, tmp_path: Path) -> None:
        """linear_enforce_cache_gate alone must not pull in the save_issue matcher."""
        generate_claude_hooks(
            tmp_path,
            force_windows=False,
            linear_enforce_cache_gate="warn",
            linear_enforce_gate=False,
        )
        settings = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        pre = [e.get("matcher") for e in settings["hooks"].get("PreToolUse", [])]
        assert "mcp__plugin_linear_linear__save_issue" not in pre

    def test_off_string_unrecognized_treated_as_off(self, tmp_path: Path) -> None:
        result = generate_claude_hooks(
            tmp_path, force_windows=False, linear_enforce_cache_gate="garbage"
        )
        assert result["linear_enforce_cache_gate"] == "off"
        assert not (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-list.sh").exists()

    def test_windows_writes_ps1_scripts(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=True, linear_enforce_cache_gate="warn")
        assert (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-list.ps1").exists()
        assert (tmp_path / ".claude" / "hooks" / "tapps-post-linear-snapshot-get.ps1").exists()
        assert not (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-list.sh").exists()


class TestPowerShellTemplates:
    """Static checks on the .ps1 variants — content parity with the bash originals."""

    def test_ps_scripts_map_has_both(self) -> None:
        assert "tapps-pre-linear-list.ps1" in LINEAR_CACHE_GATE_SCRIPTS_PS
        assert "tapps-post-linear-snapshot-get.ps1" in LINEAR_CACHE_GATE_SCRIPTS_PS

    def test_ps_hooks_config_has_matchers(self) -> None:
        pre = [e["matcher"] for e in LINEAR_CACHE_GATE_HOOKS_CONFIG_PS["PreToolUse"]]
        post = [e["matcher"] for e in LINEAR_CACHE_GATE_HOOKS_CONFIG_PS["PostToolUse"]]
        assert "mcp__plugin_linear_linear__list_issues" in pre
        assert "mcp__tapps-mcp__tapps_linear_snapshot_get" in post

    def test_ps_pre_list_mentions_bypass_env_var(self) -> None:
        assert "TAPPS_LINEAR_SKIP_CACHE_GATE" in LINEAR_CACHE_GATE_PRE_LIST_SCRIPT_PS

    def test_ps_pre_list_has_mode_placeholder(self) -> None:
        assert "__CACHE_GATE_MODE__" in LINEAR_CACHE_GATE_PRE_LIST_SCRIPT_PS

    def test_ps_pre_list_uses_unix_epoch(self) -> None:
        assert "ToUnixTimeSeconds" in LINEAR_CACHE_GATE_PRE_LIST_SCRIPT_PS

    def test_ps_post_snapshot_writes_sentinel(self) -> None:
        assert ".linear-snapshot-sentinel-" in LINEAR_CACHE_GATE_POST_SNAPSHOT_SCRIPT_PS

    def test_ps_render_warn_bakes_mode(self) -> None:
        scripts = render_cache_gate_scripts("warn", win=True)
        assert "$mode = 'warn'" in scripts["tapps-pre-linear-list.ps1"]


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only behavioral tests")
class TestCacheGateScriptBehavior:
    """End-to-end: write scripts, invoke them with crafted JSON inputs."""

    def _setup(self, tmp_path: Path, mode: str) -> Path:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_cache_gate=mode)
        return tmp_path / ".claude" / "hooks"

    def _run(
        self,
        script: Path,
        stdin: str,
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> tuple[int, str]:
        full_env = {**os.environ, **(env or {})}
        proc = subprocess.run(
            ["/usr/bin/env", "bash", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            env=full_env,
            cwd=str(cwd or script.parent.parent.parent),
            timeout=10,
        )
        return proc.returncode, proc.stderr

    def _make_input(self, tool: str, **inp: object) -> str:
        return json.dumps({"tool_name": tool, "tool_input": inp})

    def test_post_snapshot_writes_sentinel_on_hit(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "warn")
        rc, _ = self._run(
            hooks / "tapps-post-linear-snapshot-get.sh",
            self._make_input(
                "mcp__tapps-mcp__tapps_linear_snapshot_get",
                team="T",
                project="P",
                state="open",
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        sentinels = list((tmp_path / ".tapps-mcp").glob(".linear-snapshot-sentinel-*"))
        assert len(sentinels) == 1
        assert int(sentinels[0].read_text().strip()) > 0

    def test_post_snapshot_writes_sentinel_on_miss(self, tmp_path: Path) -> None:
        # Same input shape as cached=true — the hook fires identically per
        # AC: sentinel on BOTH hit and miss responses.
        hooks = self._setup(tmp_path, "warn")
        rc, _ = self._run(
            hooks / "tapps-post-linear-snapshot-get.sh",
            self._make_input(
                "mcp__tapps-mcp__tapps_linear_snapshot_get",
                team="T",
                project="P",
                state="open",
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        assert any((tmp_path / ".tapps-mcp").glob(".linear-snapshot-sentinel-*"))

    def test_pre_list_no_sentinel_block_mode(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        rc, stderr = self._run(
            hooks / "tapps-pre-linear-list.sh",
            self._make_input(
                "mcp__plugin_linear_linear__list_issues",
                team="T",
                project="P",
                state="open",
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 2
        assert "linear-read" in stderr or "snapshot_get" in stderr

    def test_pre_list_fresh_sentinel_passes(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        # Prime the sentinel via the post-snapshot hook
        self._run(
            hooks / "tapps-post-linear-snapshot-get.sh",
            self._make_input(
                "mcp__tapps-mcp__tapps_linear_snapshot_get",
                team="T",
                project="P",
                state="open",
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        # Same slice → block mode allows
        rc, _ = self._run(
            hooks / "tapps-pre-linear-list.sh",
            self._make_input(
                "mcp__plugin_linear_linear__list_issues",
                team="T",
                project="P",
                state="open",
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0

    def test_pre_list_key_mismatch_isolation(self, tmp_path: Path) -> None:
        """A snapshot for project A must NOT unlock list_issues for project B."""
        hooks = self._setup(tmp_path, "block")
        self._run(
            hooks / "tapps-post-linear-snapshot-get.sh",
            self._make_input(
                "mcp__tapps-mcp__tapps_linear_snapshot_get",
                team="T",
                project="A",
                state="open",
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        rc, _ = self._run(
            hooks / "tapps-pre-linear-list.sh",
            self._make_input(
                "mcp__plugin_linear_linear__list_issues",
                team="T",
                project="B",
                state="open",
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 2

    def test_pre_list_warn_mode_allows_with_log(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "warn")
        rc, stderr = self._run(
            hooks / "tapps-pre-linear-list.sh",
            self._make_input(
                "mcp__plugin_linear_linear__list_issues",
                team="T",
                project="P",
                state="open",
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        assert "warn mode" in stderr
        viol_log = tmp_path / ".tapps-mcp" / ".cache-gate-violations.jsonl"
        assert viol_log.exists()
        line = viol_log.read_text(encoding="utf-8").strip().splitlines()[-1]
        entry = json.loads(line)
        assert entry["mode"] == "warn"
        assert entry["key"]

    def test_pre_list_env_bypass_logged(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        rc, _ = self._run(
            hooks / "tapps-pre-linear-list.sh",
            self._make_input(
                "mcp__plugin_linear_linear__list_issues",
                team="T",
                project="P",
                state="open",
            ),
            env={
                "CLAUDE_PROJECT_DIR": str(tmp_path),
                "TAPPS_LINEAR_SKIP_CACHE_GATE": "1",
            },
            cwd=tmp_path,
        )
        assert rc == 0
        bypass_log = tmp_path / ".tapps-mcp" / ".bypass-log.jsonl"
        assert bypass_log.exists()
        entry = json.loads(bypass_log.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert entry["bypass"] == "TAPPS_LINEAR_SKIP_CACHE_GATE"

    def test_pre_list_ignores_other_tools(self, tmp_path: Path) -> None:
        """The pre-list hook must no-op for any tool other than list_issues."""
        hooks = self._setup(tmp_path, "block")
        rc, _ = self._run(
            hooks / "tapps-pre-linear-list.sh",
            json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0

    def test_pre_list_empty_team_project_fails_open(self, tmp_path: Path) -> None:
        """No team/project context → cannot key sentinel; allow through."""
        hooks = self._setup(tmp_path, "block")
        rc, _ = self._run(
            hooks / "tapps-pre-linear-list.sh",
            self._make_input("mcp__plugin_linear_linear__list_issues"),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0

    def test_post_snapshot_ignores_other_tools(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "warn")
        rc, _ = self._run(
            hooks / "tapps-post-linear-snapshot-get.sh",
            json.dumps({"tool_name": "Bash", "tool_input": {}}),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        # No sentinel created.
        sentinels = list((tmp_path / ".tapps-mcp").glob(".linear-snapshot-sentinel-*"))
        assert sentinels == []
