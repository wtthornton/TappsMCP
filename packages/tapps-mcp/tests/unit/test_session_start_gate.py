"""Tests for the session-start enforcement gate (B + C).

Covers the opt-in ``session_start_gate`` mode (off|warn|block) on
``generate_claude_hooks``, mode-baking via the ``__SESSION_START_GATE_MODE__``
placeholder, the cooperating hook pair (``tapps-post-session-start.sh`` writer
+ ``tapps-pre-session-start-gate.sh`` gate), the compact re-prompt (C), and
behavioral end-to-end via subprocess.
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
    CLAUDE_HOOK_SCRIPTS,
    SESSION_START_GATE_HOOKS_CONFIG,
    SESSION_START_GATE_HOOKS_CONFIG_PS,
    SESSION_START_GATE_PRE_SCRIPT,
    SESSION_START_GATE_PRE_SCRIPT_PS,
    SESSION_START_GATE_SCRIPTS,
    SESSION_START_GATE_SCRIPTS_PS,
    render_session_start_gate_scripts,
)
from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks


class TestSessionStartGateConfig:
    """Static checks on the hook config and script templates."""

    def test_pretooluse_matches_tapps_family(self) -> None:
        matchers = [e["matcher"] for e in SESSION_START_GATE_HOOKS_CONFIG["PreToolUse"]]
        assert any("nlt-build" in m and "tapps-mcp" in m for m in matchers)

    def test_posttooluse_matches_session_start(self) -> None:
        matchers = [e["matcher"] for e in SESSION_START_GATE_HOOKS_CONFIG["PostToolUse"]]
        assert any("tapps_session_start" in m for m in matchers)

    def test_scripts_map_has_both(self) -> None:
        assert "tapps-pre-session-start-gate.sh" in SESSION_START_GATE_SCRIPTS
        assert "tapps-post-session-start.sh" in SESSION_START_GATE_SCRIPTS

    def test_pre_gate_has_mode_placeholder(self) -> None:
        assert "__SESSION_START_GATE_MODE__" in SESSION_START_GATE_PRE_SCRIPT

    def test_pre_gate_mentions_bypass_env_var(self) -> None:
        assert "TAPPS_SKIP_SESSION_START_GATE" in SESSION_START_GATE_PRE_SCRIPT

    def test_pre_gate_whitelists_session_start(self) -> None:
        # session_start / server_info / doctor must be allowed so the gate
        # cannot deadlock a fresh or broken session.
        assert "tapps_session_start" in SESSION_START_GATE_PRE_SCRIPT
        assert "tapps_doctor" in SESSION_START_GATE_PRE_SCRIPT

    def test_pre_gate_labels_hook_only_refusal_layer(self) -> None:
        assert "layer=hook-only/defense-in-depth" in SESSION_START_GATE_PRE_SCRIPT
        assert "layer=hook-only/defense-in-depth" in SESSION_START_GATE_PRE_SCRIPT_PS

    def test_post_writer_writes_sentinel(self) -> None:
        assert ".session-start-done-" in SESSION_START_GATE_SCRIPTS["tapps-post-session-start.sh"]

    def test_render_warn_bakes_warn(self) -> None:
        scripts = render_session_start_gate_scripts("warn")
        body = scripts["tapps-pre-session-start-gate.sh"]
        assert 'MODE="warn"' in body
        assert "__SESSION_START_GATE_MODE__" not in body

    def test_render_block_bakes_block(self) -> None:
        scripts = render_session_start_gate_scripts("block")
        assert 'MODE="block"' in scripts["tapps-pre-session-start-gate.sh"]

    def test_render_unknown_mode_falls_back_to_warn(self) -> None:
        scripts = render_session_start_gate_scripts("garbage")
        assert 'MODE="warn"' in scripts["tapps-pre-session-start-gate.sh"]

    def test_compact_hook_reprompts_session_start(self) -> None:
        # C: after compaction the compact hook re-prompts for session_start.
        assert "tapps_session_start" in CLAUDE_HOOK_SCRIPTS["tapps-session-compact.sh"]


class TestSessionStartGateFlagWiring:
    """The ``session_start_gate`` mode plumbs scripts + matchers correctly."""

    def test_off_by_default(self, tmp_path: Path) -> None:
        result = generate_claude_hooks(tmp_path, force_windows=False)
        assert result["session_start_gate"] == "off"
        assert not (tmp_path / ".claude" / "hooks" / "tapps-pre-session-start-gate.sh").exists()
        assert not (tmp_path / ".claude" / "hooks" / "tapps-post-session-start.sh").exists()

    def test_warn_writes_both_scripts(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, session_start_gate="warn")
        assert (tmp_path / ".claude" / "hooks" / "tapps-pre-session-start-gate.sh").exists()
        assert (tmp_path / ".claude" / "hooks" / "tapps-post-session-start.sh").exists()

    def test_block_bakes_mode(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, session_start_gate="block")
        body = (tmp_path / ".claude" / "hooks" / "tapps-pre-session-start-gate.sh").read_text(
            encoding="utf-8"
        )
        assert 'MODE="block"' in body

    def test_warn_adds_matchers_to_settings(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, session_start_gate="warn")
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        pre = [e.get("matcher") for e in settings["hooks"].get("PreToolUse", [])]
        post = [e.get("matcher") for e in settings["hooks"].get("PostToolUse", [])]
        assert any("nlt-build" in (m or "") for m in pre)
        assert any("tapps_session_start" in (m or "") for m in post)

    def test_unknown_mode_treated_as_off(self, tmp_path: Path) -> None:
        result = generate_claude_hooks(tmp_path, force_windows=False, session_start_gate="garbage")
        assert result["session_start_gate"] == "off"
        assert not (tmp_path / ".claude" / "hooks" / "tapps-pre-session-start-gate.sh").exists()

    def test_independent_of_cache_gate(self, tmp_path: Path) -> None:
        """session_start_gate alone must not pull in the Linear cache-gate scripts."""
        generate_claude_hooks(tmp_path, force_windows=False, session_start_gate="block")
        assert not (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-list.sh").exists()

    def test_windows_writes_ps1_scripts(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=True, session_start_gate="block")
        assert (tmp_path / ".claude" / "hooks" / "tapps-pre-session-start-gate.ps1").exists()
        assert (tmp_path / ".claude" / "hooks" / "tapps-post-session-start.ps1").exists()
        assert not (tmp_path / ".claude" / "hooks" / "tapps-pre-session-start-gate.sh").exists()


class TestSessionStartGateResolved:
    """Engagement-aware defaulting of ``session_start_gate_resolved``."""

    def test_explicit_value_wins(self) -> None:
        s = TappsMCPSettings(session_start_gate="block")
        assert s.session_start_gate_resolved() == "block"

    def test_default_warn_at_medium(self) -> None:
        s = TappsMCPSettings(llm_engagement_level="medium")
        assert s.session_start_gate_resolved() == "warn"

    def test_default_off_at_low(self) -> None:
        s = TappsMCPSettings(llm_engagement_level="low")
        assert s.session_start_gate_resolved() == "off"


class TestPowerShellTemplates:
    """Static checks on the .ps1 variants."""

    def test_ps_scripts_map_has_both(self) -> None:
        assert "tapps-pre-session-start-gate.ps1" in SESSION_START_GATE_SCRIPTS_PS
        assert "tapps-post-session-start.ps1" in SESSION_START_GATE_SCRIPTS_PS

    def test_ps_hooks_config_has_matchers(self) -> None:
        pre = [e["matcher"] for e in SESSION_START_GATE_HOOKS_CONFIG_PS["PreToolUse"]]
        post = [e["matcher"] for e in SESSION_START_GATE_HOOKS_CONFIG_PS["PostToolUse"]]
        assert any("nlt-build" in m for m in pre)
        assert any("tapps_session_start" in m for m in post)

    def test_ps_pre_gate_has_mode_placeholder(self) -> None:
        assert "__SESSION_START_GATE_MODE__" in SESSION_START_GATE_PRE_SCRIPT_PS

    def test_ps_render_block_bakes_mode(self) -> None:
        scripts = render_session_start_gate_scripts("block", win=True)
        assert "$mode = 'block'" in scripts["tapps-pre-session-start-gate.ps1"]


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only behavioral tests")
class TestSessionStartGateScriptBehavior:
    """End-to-end: write scripts, invoke them with crafted JSON inputs."""

    def _setup(self, tmp_path: Path, mode: str) -> Path:
        generate_claude_hooks(tmp_path, force_windows=False, session_start_gate=mode)
        return tmp_path / ".claude" / "hooks"

    def _run(
        self,
        script: Path,
        payload: dict[str, object],
        *,
        env: dict[str, str] | None = None,
        cwd: Path,
    ) -> tuple[int, str]:
        full_env = {**os.environ, **(env or {})}
        proc = subprocess.run(
            ["/usr/bin/env", "bash", str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=full_env,
            cwd=str(cwd),
            timeout=10,
        )
        return proc.returncode, proc.stderr

    def test_block_blocks_quality_tool_without_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        rc, err = self._run(
            hooks / "tapps-pre-session-start-gate.sh",
            {"tool_name": "mcp__nlt-build__tapps_quick_check", "session_id": "s1"},
            cwd=tmp_path,
        )
        assert rc == 2
        assert "session-start gate (block)" in err

    def test_session_start_itself_allowed(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        rc, _ = self._run(
            hooks / "tapps-pre-session-start-gate.sh",
            {"tool_name": "mcp__nlt-build__tapps_session_start", "session_id": "s1"},
            cwd=tmp_path,
        )
        assert rc == 0

    def test_writer_then_gate_passes(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        rc, _ = self._run(
            hooks / "tapps-post-session-start.sh",
            {"tool_name": "mcp__nlt-build__tapps_session_start", "session_id": "s1"},
            cwd=tmp_path,
        )
        assert rc == 0
        assert (tmp_path / ".tapps-mcp" / ".session-start-done-s1").exists()
        rc, _ = self._run(
            hooks / "tapps-pre-session-start-gate.sh",
            {"tool_name": "mcp__nlt-build__tapps_quick_check", "session_id": "s1"},
            cwd=tmp_path,
        )
        assert rc == 0

    def test_sentinel_is_per_session(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        self._run(
            hooks / "tapps-post-session-start.sh",
            {"tool_name": "mcp__nlt-build__tapps_session_start", "session_id": "s1"},
            cwd=tmp_path,
        )
        # A different session_id must still be blocked.
        rc, _ = self._run(
            hooks / "tapps-pre-session-start-gate.sh",
            {"tool_name": "mcp__nlt-build__tapps_quick_check", "session_id": "s2"},
            cwd=tmp_path,
        )
        assert rc == 2

    def test_bypass_env_allows(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        rc, _ = self._run(
            hooks / "tapps-pre-session-start-gate.sh",
            {"tool_name": "mcp__nlt-build__tapps_quick_check", "session_id": "s1"},
            env={"TAPPS_SKIP_SESSION_START_GATE": "1"},
            cwd=tmp_path,
        )
        assert rc == 0
        assert (tmp_path / ".tapps-mcp" / ".bypass-log.jsonl").exists()

    def test_foreign_tool_untouched(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        rc, _ = self._run(
            hooks / "tapps-pre-session-start-gate.sh",
            {"tool_name": "Read", "session_id": "s1"},
            cwd=tmp_path,
        )
        assert rc == 0

    def test_missing_session_id_fails_open(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "block")
        rc, _ = self._run(
            hooks / "tapps-pre-session-start-gate.sh",
            {"tool_name": "mcp__nlt-build__tapps_quick_check"},
            cwd=tmp_path,
        )
        assert rc == 0

    def test_warn_allows_but_logs(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path, "warn")
        rc, err = self._run(
            hooks / "tapps-pre-session-start-gate.sh",
            {"tool_name": "mcp__nlt-build__tapps_quick_check", "session_id": "s1"},
            cwd=tmp_path,
        )
        assert rc == 0
        assert "warn" in err
        assert (tmp_path / ".tapps-mcp" / ".session-start-gate-violations.jsonl").exists()
