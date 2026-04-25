"""Tests for the UserPromptSubmit pipeline-state hook (TAP-975).

Covers:

1. Sidecar writers (``write_session_start_marker``, ``write_checklist_state_marker``).
2. Script content (bash + PS) — references both sidecars, 1800s window, /tapps-finish-task.
3. Behavioral end-to-end on Unix: stale state → reminder; fresh state → silent.
4. Engagement gating — high+medium include UserPromptSubmit, low does not.
5. Hooks-config wiring — both bash and PS configs include the matcher.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS_PS,
    CLAUDE_HOOKS_CONFIG,
    CLAUDE_HOOKS_CONFIG_PS,
    ENGAGEMENT_HOOK_EVENTS,
)
from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks
from tapps_mcp.server_helpers import (
    write_checklist_state_marker,
    write_session_start_marker,
)


class TestSidecarWriters:
    def test_session_start_marker_writes_epoch(self, tmp_path: Path) -> None:
        write_session_start_marker(tmp_path)
        marker = tmp_path / ".tapps-mcp" / ".session-start-marker"
        assert marker.exists()
        ts = int(marker.read_text(encoding="utf-8").strip())
        # Within 5s of "now" — generous to absorb test environment lag.
        assert abs(ts - int(time.time())) < 5

    def test_session_start_marker_creates_parent_dir(self, tmp_path: Path) -> None:
        # Sub-directory does not exist yet; writer must mkdir -p.
        target = tmp_path / "fresh"
        target.mkdir()
        write_session_start_marker(target)
        assert (target / ".tapps-mcp" / ".session-start-marker").exists()

    def test_session_start_marker_swallows_errors(self) -> None:
        # Pass a path that cannot be written under (file-not-dir).
        # Writer must not raise.
        write_session_start_marker("/dev/null/cannot-mkdir-here")

    def test_checklist_state_marker_writes_json(self, tmp_path: Path) -> None:
        write_checklist_state_marker(
            tmp_path,
            complete=False,
            missing_required=["tapps_score_file", "tapps_quality_gate"],
        )
        path = tmp_path / ".tapps-mcp" / ".checklist-state.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["complete"] is False
        assert data["missing_required"] == [
            "tapps_score_file",
            "tapps_quality_gate",
        ]
        assert isinstance(data["ts"], int)

    def test_checklist_state_marker_complete(self, tmp_path: Path) -> None:
        write_checklist_state_marker(tmp_path, complete=True)
        data = json.loads(
            (tmp_path / ".tapps-mcp" / ".checklist-state.json").read_text(
                encoding="utf-8"
            )
        )
        assert data["complete"] is True
        assert data["missing_required"] == []


class TestScriptContent:
    """Static content checks on both bash + PS variants."""

    def test_bash_script_exists(self) -> None:
        assert "tapps-user-prompt-submit.sh" in CLAUDE_HOOK_SCRIPTS

    def test_ps_script_exists(self) -> None:
        assert "tapps-user-prompt-submit.ps1" in CLAUDE_HOOK_SCRIPTS_PS

    def test_bash_references_both_sidecars(self) -> None:
        body = CLAUDE_HOOK_SCRIPTS["tapps-user-prompt-submit.sh"]
        assert ".session-start-marker" in body
        assert ".checklist-state.json" in body

    def test_ps_references_both_sidecars(self) -> None:
        body = CLAUDE_HOOK_SCRIPTS_PS["tapps-user-prompt-submit.ps1"]
        assert ".session-start-marker" in body
        assert ".checklist-state.json" in body

    def test_bash_uses_1800s_window(self) -> None:
        # The AC's "30 minute" freshness check.
        assert "1800" in CLAUDE_HOOK_SCRIPTS["tapps-user-prompt-submit.sh"]

    def test_ps_uses_1800s_window(self) -> None:
        assert "1800" in CLAUDE_HOOK_SCRIPTS_PS["tapps-user-prompt-submit.ps1"]

    def test_bash_mentions_finish_task(self) -> None:
        body = CLAUDE_HOOK_SCRIPTS["tapps-user-prompt-submit.sh"]
        assert "/tapps-finish-task" in body

    def test_ps_mentions_finish_task(self) -> None:
        body = CLAUDE_HOOK_SCRIPTS_PS["tapps-user-prompt-submit.ps1"]
        assert "/tapps-finish-task" in body

    def test_bash_exits_zero(self) -> None:
        # UserPromptSubmit advisory only — exit 2 would block the prompt.
        assert "exit 0" in CLAUDE_HOOK_SCRIPTS["tapps-user-prompt-submit.sh"]
        assert "exit 2" not in CLAUDE_HOOK_SCRIPTS["tapps-user-prompt-submit.sh"]

    def test_ps_exits_zero(self) -> None:
        assert "exit 0" in CLAUDE_HOOK_SCRIPTS_PS["tapps-user-prompt-submit.ps1"]
        assert "exit 2" not in CLAUDE_HOOK_SCRIPTS_PS["tapps-user-prompt-submit.ps1"]


class TestHooksConfigWiring:
    def test_bash_hooks_config_has_user_prompt_submit(self) -> None:
        entries = CLAUDE_HOOKS_CONFIG.get("UserPromptSubmit", [])
        cmds = [h["command"] for entry in entries for h in entry.get("hooks", [])]
        assert any("tapps-user-prompt-submit.sh" in c for c in cmds)

    def test_ps_hooks_config_has_user_prompt_submit(self) -> None:
        entries = CLAUDE_HOOKS_CONFIG_PS.get("UserPromptSubmit", [])
        cmds = [h["command"] for entry in entries for h in entry.get("hooks", [])]
        assert any(
            "powershell -NoProfile" in c and "tapps-user-prompt-submit.ps1" in c
            for c in cmds
        )


class TestEngagementGating:
    def test_high_includes_user_prompt_submit(self) -> None:
        assert "UserPromptSubmit" in ENGAGEMENT_HOOK_EVENTS["high"]

    def test_medium_includes_user_prompt_submit(self) -> None:
        assert "UserPromptSubmit" in ENGAGEMENT_HOOK_EVENTS["medium"]

    def test_low_excludes_user_prompt_submit(self) -> None:
        assert "UserPromptSubmit" not in ENGAGEMENT_HOOK_EVENTS["low"]

    def test_high_writes_script_to_disk(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="high")
        assert (
            tmp_path / ".claude" / "hooks" / "tapps-user-prompt-submit.sh"
        ).exists()

    def test_medium_writes_script_to_disk(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="medium")
        assert (
            tmp_path / ".claude" / "hooks" / "tapps-user-prompt-submit.sh"
        ).exists()

    def test_low_does_not_write_script(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="low")
        assert not (
            tmp_path / ".claude" / "hooks" / "tapps-user-prompt-submit.sh"
        ).exists()

    def test_high_settings_includes_matcher(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="high")
        settings = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        cmds = [
            h.get("command", "")
            for entry in settings["hooks"].get("UserPromptSubmit", [])
            for h in entry.get("hooks", [])
        ]
        assert any("tapps-user-prompt-submit.sh" in c for c in cmds)

    def test_low_settings_omits_event(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="low")
        settings = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        # UserPromptSubmit must not appear at low engagement.
        assert "UserPromptSubmit" not in settings.get("hooks", {})


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only end-to-end")
class TestBehavior:
    """End-to-end: write the script, invoke it with crafted sidecar state."""

    def _setup(self, tmp_path: Path) -> Path:
        generate_claude_hooks(tmp_path, force_windows=False, engagement_level="high")
        return tmp_path / ".claude" / "hooks" / "tapps-user-prompt-submit.sh"

    def _run(
        self,
        script: Path,
        stdin: str = "",
        *,
        env: dict[str, str] | None = None,
        cwd: Path | None = None,
    ) -> tuple[int, str, str]:
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
        return proc.returncode, proc.stdout, proc.stderr

    def test_no_sidecars_yields_session_start_reminder(self, tmp_path: Path) -> None:
        script = self._setup(tmp_path)
        rc, _, stderr = self._run(
            script, stdin="{}", env={"CLAUDE_PROJECT_DIR": str(tmp_path)}
        )
        assert rc == 0
        assert "tapps_session_start" in stderr

    def test_fresh_session_marker_no_checklist_is_silent(self, tmp_path: Path) -> None:
        write_session_start_marker(tmp_path)
        script = self._setup(tmp_path)
        rc, _, stderr = self._run(
            script, stdin="{}", env={"CLAUDE_PROJECT_DIR": str(tmp_path)}
        )
        assert rc == 0
        assert stderr.strip() == ""

    def test_stale_session_marker_warns(self, tmp_path: Path) -> None:
        # 31 minutes ago — past the 1800s window.
        sidecar = tmp_path / ".tapps-mcp"
        sidecar.mkdir()
        (sidecar / ".session-start-marker").write_text(
            str(int(time.time()) - 31 * 60), encoding="utf-8"
        )
        script = self._setup(tmp_path)
        rc, _, stderr = self._run(
            script, stdin="{}", env={"CLAUDE_PROJECT_DIR": str(tmp_path)}
        )
        assert rc == 0
        assert "tapps_session_start" in stderr

    def test_open_checklist_warns_even_when_session_fresh(
        self, tmp_path: Path
    ) -> None:
        write_session_start_marker(tmp_path)
        write_checklist_state_marker(
            tmp_path,
            complete=False,
            missing_required=["tapps_quality_gate"],
        )
        script = self._setup(tmp_path)
        rc, _, stderr = self._run(
            script, stdin="{}", env={"CLAUDE_PROJECT_DIR": str(tmp_path)}
        )
        assert rc == 0
        assert "tapps_checklist" in stderr
        assert "tapps_quality_gate" in stderr
        assert "/tapps-finish-task" in stderr

    def test_complete_checklist_does_not_warn(self, tmp_path: Path) -> None:
        write_session_start_marker(tmp_path)
        write_checklist_state_marker(tmp_path, complete=True)
        script = self._setup(tmp_path)
        rc, _, stderr = self._run(
            script, stdin="{}", env={"CLAUDE_PROJECT_DIR": str(tmp_path)}
        )
        assert rc == 0
        assert stderr.strip() == ""

    def test_garbled_marker_treated_as_stale(self, tmp_path: Path) -> None:
        sidecar = tmp_path / ".tapps-mcp"
        sidecar.mkdir()
        (sidecar / ".session-start-marker").write_text("not-a-number", encoding="utf-8")
        script = self._setup(tmp_path)
        rc, _, stderr = self._run(
            script, stdin="{}", env={"CLAUDE_PROJECT_DIR": str(tmp_path)}
        )
        assert rc == 0
        assert "tapps_session_start" in stderr
