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
    LINEAR_GATE_POST_VALIDATE_SCRIPT,
    LINEAR_GATE_PRE_SAVE_SCRIPT,
    LINEAR_GATE_SCRIPTS,
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
        settings = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        pre_matchers = [e.get("matcher") for e in settings["hooks"].get("PreToolUse", [])]
        post_matchers = [e.get("matcher") for e in settings["hooks"].get("PostToolUse", [])]
        assert "mcp__plugin_linear_linear__save_issue" in pre_matchers
        assert "mcp__docs-mcp__docs_validate_linear_issue" in post_matchers

    def test_independent_of_destructive_guard(self, tmp_path: Path) -> None:
        """linear_enforce_gate alone must not pull in the Bash matcher."""
        generate_claude_hooks(tmp_path, force_windows=False, linear_enforce_gate=True)
        settings = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        pre_matchers = [e.get("matcher") for e in settings["hooks"].get("PreToolUse", [])]
        assert "Bash" not in pre_matchers

    def test_windows_silently_disables(self, tmp_path: Path) -> None:
        """Bash-only scripts — Windows gets no-op until PS variants ship."""
        result = generate_claude_hooks(
            tmp_path, force_windows=True, linear_enforce_gate=True
        )
        assert result["linear_enforce_gate"] is False
        assert not (
            tmp_path / ".claude" / "hooks" / "tapps-pre-linear-write.sh"
        ).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="bash-only gate scripts")
class TestGateScriptBehavior:
    """End-to-end: write scripts, invoke them with crafted inputs."""

    def _setup(self, tmp_path: Path) -> Path:
        generate_claude_hooks(
            tmp_path, force_windows=False, linear_enforce_gate=True
        )
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
        hooks = self._setup(tmp_path)
        script = hooks / "tapps-post-docs-validate.sh"
        rc, _ = self._run(
            script,
            json.dumps({"tool_name": "mcp__docs-mcp__docs_validate_linear_issue"}),
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

        (tmp_path / ".tapps-mcp" / ".linear-validate-sentinel").write_text(
            str(int(_time.time()))
        )
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
