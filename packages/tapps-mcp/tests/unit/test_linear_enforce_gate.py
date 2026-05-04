"""Tests for the Linear routing gate (TAP-981).

Covers the opt-in ``linear_enforce_gate`` flag on ``generate_claude_hooks``,
its wiring through the bootstrap pipeline, and the two cooperating hooks
(``tapps-post-docs-validate.sh`` + ``tapps-pre-linear-write.sh``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_hook_templates import (
    LINEAR_GATE_HOOKS_CONFIG,
    LINEAR_GATE_HOOKS_CONFIG_PS,
    LINEAR_GATE_POST_VALIDATE_SCRIPT,
    LINEAR_GATE_POST_VALIDATE_SCRIPT_PS,
    LINEAR_GATE_PRE_SAVE_SCRIPT,
    LINEAR_GATE_PRE_SAVE_SCRIPT_PS,
    LINEAR_GATE_SCRIPTS,
    LINEAR_GATE_SCRIPTS_PS,
)
from tapps_mcp.pipeline.platform_hooks import generate_claude_hooks


class TestGateHooksConfig:
    """Static checks on the hook config shape."""

    def test_has_pretooluse_save_issue_matcher(self) -> None:
        entries = LINEAR_GATE_HOOKS_CONFIG["PreToolUse"]
        matchers = [e["matcher"] for e in entries]
        assert "mcp__plugin_linear_linear__save_issue" in matchers

    def test_has_posttooluse_validate_matcher(self) -> None:
        entries = LINEAR_GATE_HOOKS_CONFIG["PostToolUse"]
        matchers = [e["matcher"] for e in entries]
        assert "mcp__docs-mcp__docs_validate_linear_issue" in matchers

    def test_scripts_map_has_both(self) -> None:
        assert "tapps-pre-linear-write.sh" in LINEAR_GATE_SCRIPTS
        assert "tapps-post-docs-validate.sh" in LINEAR_GATE_SCRIPTS

    def test_pre_save_script_mentions_bypass_env_var(self) -> None:
        assert "TAPPS_LINEAR_SKIP_VALIDATE" in LINEAR_GATE_PRE_SAVE_SCRIPT

    def test_pre_save_script_references_linear_standards_rule(self) -> None:
        assert "linear-standards.md" in LINEAR_GATE_PRE_SAVE_SCRIPT

    def test_post_validate_script_writes_sentinel(self) -> None:
        assert ".linear-validate-sentinel" in LINEAR_GATE_POST_VALIDATE_SCRIPT


class TestGateFlagWiring:
    """The ``linear_enforce_gate`` param plumbs scripts + matchers correctly."""

    def test_off_by_default(self, tmp_path: Path) -> None:
        result = generate_claude_hooks(tmp_path, force_windows=False)
        assert result["linear_enforce_gate"] is False
        assert not (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh").exists()
        assert not (tmp_path / ".claude" / "hooks" / "tapps-post-docs-validate.sh").exists()

    def test_on_writes_both_scripts(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_gate=True)
        assert (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh").exists()
        assert (tmp_path / ".claude" / "hooks" / "tapps-post-docs-validate.sh").exists()

    def test_on_adds_matchers_to_settings(self, tmp_path: Path) -> None:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_gate=True)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        pre_matchers = [e.get("matcher") for e in settings["hooks"].get("PreToolUse", [])]
        post_matchers = [e.get("matcher") for e in settings["hooks"].get("PostToolUse", [])]
        assert "mcp__plugin_linear_linear__save_issue" in pre_matchers
        assert "mcp__docs-mcp__docs_validate_linear_issue" in post_matchers

    def test_independent_of_destructive_guard(self, tmp_path: Path) -> None:
        """linear_enforce_gate alone must not pull in the Bash matcher."""
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_gate=True)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        pre_matchers = [e.get("matcher") for e in settings["hooks"].get("PreToolUse", [])]
        assert "Bash" not in pre_matchers

    def test_windows_writes_ps1_scripts(self, tmp_path: Path) -> None:
        """TAP-986: Windows opt-in now produces .ps1 gate scripts, not no-op."""
        result = generate_claude_hooks(tmp_path, force_windows=True, linear_enforce_gate=True)
        assert result["linear_enforce_gate"] is True
        assert (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.ps1").exists()
        assert (tmp_path / ".claude" / "hooks" / "tapps-post-docs-validate.ps1").exists()
        # And the bash scripts must NOT land on Windows — wrong-platform files
        # would be cleaned up by _cleanup_wrong_platform_scripts.
        assert not (tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh").exists()

    def test_windows_settings_points_at_powershell(self, tmp_path: Path) -> None:
        """Windows hooks config must invoke powershell -File ... .ps1."""
        generate_claude_hooks(tmp_path, force_windows=True, linear_enforce_gate=True)
        settings = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))

        def _cmds(event: str) -> list[str]:
            out: list[str] = []
            for entry in settings["hooks"].get(event, []):
                for hook in entry.get("hooks", []):
                    out.append(hook.get("command", ""))
            return out

        pre_cmds = _cmds("PreToolUse")
        post_cmds = _cmds("PostToolUse")
        assert any(
            "powershell -NoProfile" in c and "tapps-pre-linear-write.ps1" in c for c in pre_cmds
        )
        assert any(
            "powershell -NoProfile" in c and "tapps-post-docs-validate.ps1" in c for c in post_cmds
        )


class TestGatePowerShellScripts:
    """Static checks on the PS variants (TAP-986).

    Behavioral tests run only on Windows — on Unix we assert content to keep
    parity with the bash originals without invoking powershell.
    """

    def test_scripts_ps_map_has_both(self) -> None:
        assert "tapps-pre-linear-write.ps1" in LINEAR_GATE_SCRIPTS_PS
        assert "tapps-post-docs-validate.ps1" in LINEAR_GATE_SCRIPTS_PS

    def test_ps_hooks_config_has_matchers(self) -> None:
        pre_matchers = [e["matcher"] for e in LINEAR_GATE_HOOKS_CONFIG_PS["PreToolUse"]]
        post_matchers = [e["matcher"] for e in LINEAR_GATE_HOOKS_CONFIG_PS["PostToolUse"]]
        assert "mcp__plugin_linear_linear__save_issue" in pre_matchers
        assert "mcp__docs-mcp__docs_validate_linear_issue" in post_matchers

    def test_ps_pre_save_script_mentions_bypass_env_var(self) -> None:
        assert "TAPPS_LINEAR_SKIP_VALIDATE" in LINEAR_GATE_PRE_SAVE_SCRIPT_PS

    def test_ps_pre_save_script_references_linear_standards_rule(self) -> None:
        assert "linear-standards.md" in LINEAR_GATE_PRE_SAVE_SCRIPT_PS

    def test_ps_post_validate_script_writes_sentinel(self) -> None:
        assert ".linear-validate-sentinel" in LINEAR_GATE_POST_VALIDATE_SCRIPT_PS

    def test_ps_pre_save_enforces_1800s_window(self) -> None:
        # Must match the bash freshness window so behavior is identical.
        assert "1800" in LINEAR_GATE_PRE_SAVE_SCRIPT_PS

    def test_ps_pre_save_logs_bypass(self) -> None:
        assert ".bypass-log.jsonl" in LINEAR_GATE_PRE_SAVE_SCRIPT_PS

    def test_ps_pre_save_has_update_only_allowlist(self) -> None:
        """TAP-981 FP reduction: PS variant must implement the same allow-list."""
        assert "updateOnly" in LINEAR_GATE_PRE_SAVE_SCRIPT_PS
        assert "hasId" in LINEAR_GATE_PRE_SAVE_SCRIPT_PS
        assert "hasTemplate" in LINEAR_GATE_PRE_SAVE_SCRIPT_PS

    def test_bash_pre_save_has_update_only_allowlist(self) -> None:
        assert "UPDATE_ONLY" in LINEAR_GATE_PRE_SAVE_SCRIPT
        assert "has_id" in LINEAR_GATE_PRE_SAVE_SCRIPT
        assert "has_template" in LINEAR_GATE_PRE_SAVE_SCRIPT

    def test_ps_scripts_use_unix_epoch(self) -> None:
        # PS equivalent of bash `date +%s` is DateTimeOffset.ToUnixTimeSeconds.
        assert "ToUnixTimeSeconds" in LINEAR_GATE_POST_VALIDATE_SCRIPT_PS
        assert "ToUnixTimeSeconds" in LINEAR_GATE_PRE_SAVE_SCRIPT_PS

    def test_ps_hooks_config_ps_uses_powershell_prefix(self) -> None:
        for entries in LINEAR_GATE_HOOKS_CONFIG_PS.values():
            for entry in entries:
                for hook in entry["hooks"]:
                    assert "powershell -NoProfile" in hook["command"]
                    assert hook["command"].endswith(".ps1")


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only gate scripts")
class TestGateScriptBehavior:
    """End-to-end: write scripts, invoke them with crafted inputs."""

    def _setup(self, tmp_path: Path) -> Path:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_gate=True)
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

    def test_post_validate_writes_sentinel(self, tmp_path: Path) -> None:
        # TAP-1328: post-docs-validate.sh now requires
        # tool_response.data.agent_ready==true before writing the sentinel,
        # so passing only tool_name (the pre-1328 contract) no longer
        # produces a sentinel. Send a complete validator response.
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-post-docs-validate.sh"
        rc, _ = self._run(
            script,
            json.dumps(
                {
                    "tool_name": "mcp__docs-mcp__docs_validate_linear_issue",
                    "tool_response": {"data": {"agent_ready": True}},
                }
            ),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        sentinel = tmp_path / ".tapps-mcp" / ".linear-validate-sentinel"
        assert sentinel.exists()
        ts = int(sentinel.read_text().strip())
        assert ts > 0

    def test_post_validate_ignores_other_tools(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-post-docs-validate.sh"
        rc, _ = self._run(
            script,
            json.dumps({"tool_name": "mcp__some-other-tool"}),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0
        sentinel = tmp_path / ".tapps-mcp" / ".linear-validate-sentinel"
        assert not sentinel.exists()

    def test_pre_save_blocks_without_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, stderr = self._run(
            script,
            json.dumps({"tool_name": "mcp__plugin_linear_linear__save_issue"}),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 2
        assert "linear-issue" in stderr
        assert "docs_validate_linear_issue" in stderr

    def test_pre_save_allows_with_fresh_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        (tmp_path / ".tapps-mcp").mkdir(exist_ok=True)
        import time as _time

        (tmp_path / ".tapps-mcp" / ".linear-validate-sentinel").write_text(str(int(_time.time())))
        script = hooks / "tapps-pre-linear-write.sh"
        rc, _ = self._run(
            script,
            json.dumps({"tool_name": "mcp__plugin_linear_linear__save_issue"}),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0

    def test_pre_save_blocks_stale_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        (tmp_path / ".tapps-mcp").mkdir(exist_ok=True)
        import time as _time

        # 31 minutes in the past — past the 1800s freshness window
        (tmp_path / ".tapps-mcp" / ".linear-validate-sentinel").write_text(
            str(int(_time.time()) - 31 * 60)
        )
        script = hooks / "tapps-pre-linear-write.sh"
        rc, stderr = self._run(
            script,
            json.dumps({"tool_name": "mcp__plugin_linear_linear__save_issue"}),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 2
        assert "1800s" in stderr or "freshness" in stderr

    def test_pre_save_bypass_env_allows_and_logs(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, _ = self._run(
            script,
            json.dumps({"tool_name": "mcp__plugin_linear_linear__save_issue"}),
            env={
                "CLAUDE_PROJECT_DIR": str(tmp_path),
                "TAPPS_LINEAR_SKIP_VALIDATE": "1",
            },
            cwd=tmp_path,
        )
        assert rc == 0
        log = tmp_path / ".tapps-mcp" / ".bypass-log.jsonl"
        assert log.exists()
        entry = json.loads(log.read_text().strip())
        assert entry["bypass"] == "TAPPS_LINEAR_SKIP_VALIDATE"

    def test_pre_save_ignores_non_save_issue_tools(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, _ = self._run(
            script,
            json.dumps({"tool_name": "Bash"}),
            env={"CLAUDE_PROJECT_DIR": str(tmp_path)},
            cwd=tmp_path,
        )
        assert rc == 0


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only gate scripts")
class TestUpdateOnlyAllowlist:
    """TAP-981 FP-reduction: metadata-only updates skip the sentinel.

    A save_issue call that targets an existing issue (id present) and does NOT
    modify title or description is treated as a pure metadata update — status,
    priority, label, assignee changes don't need a fresh template validation.
    Drives the false-positive rate on legitimate updates below the 5% bar.
    """

    def _setup(self, tmp_path: Path) -> Path:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_gate=True)
        return tmp_path / ".claude" / "hooks"

    def _run(self, script: Path, stdin: str, cwd: Path) -> tuple[int, str]:
        full_env = {**os.environ, "CLAUDE_PROJECT_DIR": str(cwd)}
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

    def test_status_update_allowed_without_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, _ = self._run(
            script,
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {"id": "TAP-123", "state": "In Progress"},
                }
            ),
            tmp_path,
        )
        assert rc == 0

    def test_priority_update_allowed_without_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, _ = self._run(
            script,
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {"id": "TAP-123", "priority": 1},
                }
            ),
            tmp_path,
        )
        assert rc == 0

    def test_label_update_allowed_without_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, _ = self._run(
            script,
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {"id": "TAP-123", "labels": ["bug", "p0"]},
                }
            ),
            tmp_path,
        )
        assert rc == 0

    def test_assignee_update_allowed_without_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, _ = self._run(
            script,
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {"id": "TAP-123", "assignee": "agent_user"},
                }
            ),
            tmp_path,
        )
        assert rc == 0

    def test_title_change_still_requires_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, stderr = self._run(
            script,
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {"id": "TAP-123", "title": "New title"},
                }
            ),
            tmp_path,
        )
        assert rc == 2
        assert "linear-issue" in stderr

    def test_description_change_still_requires_sentinel(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, stderr = self._run(
            script,
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {
                        "id": "TAP-123",
                        "description": "Replacement body",
                    },
                }
            ),
            tmp_path,
        )
        assert rc == 2
        assert "linear-issue" in stderr

    def test_create_without_id_still_requires_sentinel(self, tmp_path: Path) -> None:
        """No id means the call is a create — sentinel still required."""
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        rc, _ = self._run(
            script,
            json.dumps(
                {
                    "tool_name": "mcp__plugin_linear_linear__save_issue",
                    "tool_input": {"title": "New issue", "team": "TAP"},
                }
            ),
            tmp_path,
        )
        assert rc == 2


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only gate scripts")
class TestGateScriptPerf:
    """The pre-save gate must run in <100ms — it sits in front of every Linear
    write and any latency taxes the user.

    The acceptance criterion is a single-call <100ms budget. We measure several
    runs and assert the median is well under budget so a single GC pause or
    cold subprocess doesn't flake the test.
    """

    PERF_BUDGET_MS = 100
    PERF_RUNS = 5

    def _setup(self, tmp_path: Path) -> Path:
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_gate=True)
        return tmp_path / ".claude" / "hooks"

    def _measure_ms(
        self,
        script: Path,
        stdin: str,
        env: dict[str, str],
        cwd: Path,
    ) -> int:
        import time as _time

        full_env = {**os.environ, **env}
        t0 = _time.perf_counter_ns()
        proc = subprocess.run(
            ["/usr/bin/env", "bash", str(script)],
            input=stdin,
            capture_output=True,
            text=True,
            env=full_env,
            cwd=str(cwd),
            timeout=10,
        )
        elapsed_ms = (_time.perf_counter_ns() - t0) // 1_000_000
        # Sanity-check the script actually executed end-to-end.
        assert proc.returncode in (0, 2), f"unexpected rc {proc.returncode}"
        return elapsed_ms

    def test_pre_save_block_path_under_100ms(self, tmp_path: Path) -> None:
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-pre-linear-write.sh"
        stdin = json.dumps({"tool_name": "mcp__plugin_linear_linear__save_issue"})
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        runs = [self._measure_ms(script, stdin, env, tmp_path) for _ in range(self.PERF_RUNS)]
        runs.sort()
        median = runs[len(runs) // 2]
        assert median < self.PERF_BUDGET_MS, (
            f"pre-save block path median={median}ms exceeds {self.PERF_BUDGET_MS}ms budget; runs={runs}"
        )

    def test_pre_save_allow_path_under_100ms(self, tmp_path: Path) -> None:
        import time as _time

        hooks = self._setup(tmp_path)
        (tmp_path / ".tapps-mcp").mkdir(exist_ok=True)
        (tmp_path / ".tapps-mcp" / ".linear-validate-sentinel").write_text(str(int(_time.time())))
        script = hooks / "tapps-pre-linear-write.sh"
        stdin = json.dumps({"tool_name": "mcp__plugin_linear_linear__save_issue"})
        env = {"CLAUDE_PROJECT_DIR": str(tmp_path)}
        runs = [self._measure_ms(script, stdin, env, tmp_path) for _ in range(self.PERF_RUNS)]
        runs.sort()
        median = runs[len(runs) // 2]
        assert median < self.PERF_BUDGET_MS, (
            f"pre-save allow path median={median}ms exceeds {self.PERF_BUDGET_MS}ms budget; runs={runs}"
        )


class TestEngagementAwareDefault:
    """linear_enforce_gate_resolved() defaults true at high/medium, false at low (TAP-981).

    User-explicit overrides in .tapps-mcp.yaml or env always win.
    """

    def test_high_defaults_to_true(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(llm_engagement_level="high")
        assert s.linear_enforce_gate_resolved() is True

    def test_medium_defaults_to_true(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(llm_engagement_level="medium")
        assert s.linear_enforce_gate_resolved() is True

    def test_low_defaults_to_false(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(llm_engagement_level="low")
        assert s.linear_enforce_gate_resolved() is False

    def test_explicit_false_at_high_respected(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(llm_engagement_level="high", linear_enforce_gate=False)
        assert s.linear_enforce_gate_resolved() is False

    def test_explicit_true_at_low_respected(self) -> None:
        from tapps_core.config.settings import TappsMCPSettings

        s = TappsMCPSettings(llm_engagement_level="low", linear_enforce_gate=True)
        assert s.linear_enforce_gate_resolved() is True


class TestDoctorMatchersCheck:
    """check_pretooluse_matchers reports each matcher by name."""

    def test_empty_when_no_settings(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_pretooluse_matchers

        result = check_pretooluse_matchers(tmp_path)
        assert result.ok is True
        assert "not present" in result.message or "no matchers" in result.message

    def test_lists_each_matcher(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_pretooluse_matchers

        generate_claude_hooks(
            tmp_path,
            force_windows=False,
            destructive_guard=True,
            linear_enforce_gate=True,
        )
        result = check_pretooluse_matchers(tmp_path)
        assert result.ok is True
        assert "Bash" in result.message
        assert "mcp__plugin_linear_linear__save_issue" in result.message

    def test_reports_no_matchers_cleanly(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.doctor import check_pretooluse_matchers

        generate_claude_hooks(tmp_path, force_windows=False)
        result = check_pretooluse_matchers(tmp_path)
        assert result.ok is True
        assert "no PreToolUse matchers" in result.message

    def test_flags_missing_linear_gate_when_other_gates_present(self, tmp_path: Path) -> None:
        """destructive_guard alone must produce an explicit Linear-gate-missing note."""
        from tapps_mcp.distribution.doctor import check_pretooluse_matchers

        generate_claude_hooks(
            tmp_path,
            force_windows=False,
            destructive_guard=True,
            linear_enforce_gate=False,
        )
        result = check_pretooluse_matchers(tmp_path)
        assert result.ok is True
        assert "Bash" in result.message
        assert "Linear routing gate: NOT enabled" in result.message

    def test_flags_missing_linear_gate_when_no_matchers(self, tmp_path: Path) -> None:
        """Empty hooks block must still call out the Linear gate explicitly."""
        from tapps_mcp.distribution.doctor import check_pretooluse_matchers

        generate_claude_hooks(tmp_path, force_windows=False)
        result = check_pretooluse_matchers(tmp_path)
        assert result.ok is True
        assert "Linear routing gate: NOT enabled" in result.message

    def test_confirms_linear_gate_when_present(self, tmp_path: Path) -> None:
        """When the Linear matcher IS wired, status reads 'active'."""
        from tapps_mcp.distribution.doctor import check_pretooluse_matchers

        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_gate=True)
        result = check_pretooluse_matchers(tmp_path)
        assert result.ok is True
        assert "Linear routing gate: active" in result.message
        assert "Linear routing gate: NOT enabled" not in result.message
