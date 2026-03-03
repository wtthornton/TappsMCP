"""Tests for the PostToolUse validate hook and sidecar-aware Stop/TaskCompleted hooks."""

from __future__ import annotations

from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS_BLOCKING,
    CLAUDE_HOOK_SCRIPTS_PS,
    CLAUDE_HOOK_SCRIPTS_BLOCKING_PS,
    CLAUDE_HOOKS_CONFIG,
    CLAUDE_HOOKS_CONFIG_PS,
)


# ---------------------------------------------------------------------------
# PostToolUse validate hook template tests
# ---------------------------------------------------------------------------


class TestPostValidateHookTemplate:
    """Verify the tapps-post-validate hook script content."""

    def test_bash_script_exists(self) -> None:
        assert "tapps-post-validate.sh" in CLAUDE_HOOK_SCRIPTS

    def test_bash_script_starts_with_shebang(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-post-validate.sh"]
        assert script.startswith("#!/usr/bin/env bash")

    def test_bash_script_reads_progress_file(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-post-validate.sh"]
        assert ".validation-progress.json" in script

    def test_bash_script_uses_claude_project_dir(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-post-validate.sh"]
        assert "CLAUDE_PROJECT_DIR" in script

    def test_bash_script_handles_completed_status(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-post-validate.sh"]
        assert "completed" in script
        assert "ALL PASSED" in script

    def test_bash_script_handles_error_status(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-post-validate.sh"]
        assert "error" in script

    def test_bash_script_handles_running_status(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-post-validate.sh"]
        assert "running" in script

    def test_bash_script_exits_zero(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-post-validate.sh"]
        assert "exit 0" in script
        assert "exit 2" not in script

    def test_ps_script_exists(self) -> None:
        assert "tapps-post-validate.ps1" in CLAUDE_HOOK_SCRIPTS_PS

    def test_ps_script_reads_progress_file(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_PS["tapps-post-validate.ps1"]
        assert ".validation-progress.json" in script

    def test_ps_script_handles_completed_status(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_PS["tapps-post-validate.ps1"]
        assert "completed" in script
        assert "ALL PASSED" in script


# ---------------------------------------------------------------------------
# PostToolUse hook config tests
# ---------------------------------------------------------------------------


class TestPostValidateHookConfig:
    """Verify the PostToolUse config includes the validate_changed matcher."""

    def test_bash_config_has_validate_matcher(self) -> None:
        post_tool_entries = CLAUDE_HOOKS_CONFIG["PostToolUse"]
        matchers = [e.get("matcher", "") for e in post_tool_entries]
        assert "mcp__tapps-mcp__tapps_validate_changed" in matchers

    def test_bash_config_validate_hook_has_timeout(self) -> None:
        post_tool_entries = CLAUDE_HOOKS_CONFIG["PostToolUse"]
        for entry in post_tool_entries:
            if entry.get("matcher") == "mcp__tapps-mcp__tapps_validate_changed":
                hook = entry["hooks"][0]
                assert hook.get("timeout") == 10
                break
        else:
            raise AssertionError("validate_changed matcher not found")  # noqa: TRY003

    def test_ps_config_has_validate_matcher(self) -> None:
        post_tool_entries = CLAUDE_HOOKS_CONFIG_PS["PostToolUse"]
        matchers = [e.get("matcher", "") for e in post_tool_entries]
        assert "mcp__tapps-mcp__tapps_validate_changed" in matchers

    def test_ps_config_validate_hook_has_timeout(self) -> None:
        post_tool_entries = CLAUDE_HOOKS_CONFIG_PS["PostToolUse"]
        for entry in post_tool_entries:
            if entry.get("matcher") == "mcp__tapps-mcp__tapps_validate_changed":
                hook = entry["hooks"][0]
                assert hook.get("timeout") == 10
                break
        else:
            raise AssertionError("validate_changed PS matcher not found")  # noqa: TRY003


# ---------------------------------------------------------------------------
# Stop hook sidecar-aware tests
# ---------------------------------------------------------------------------


class TestStopHookSidecarAware:
    """Verify Stop hooks read sidecar progress file."""

    def test_medium_stop_reads_progress(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-stop.sh"]
        assert ".validation-progress.json" in script

    def test_medium_stop_ps_reads_progress(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_PS["tapps-stop.ps1"]
        assert ".validation-progress.json" in script

    def test_blocking_stop_reads_progress(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-stop.sh"]
        assert ".validation-progress.json" in script

    def test_blocking_stop_ps_reads_progress(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_BLOCKING_PS["tapps-stop.ps1"]
        assert ".validation-progress.json" in script

    def test_blocking_stop_still_blocks_without_marker(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-stop.sh"]
        assert "exit 2" in script
        assert "BLOCKED" in script


# ---------------------------------------------------------------------------
# TaskCompleted hook sidecar-aware tests
# ---------------------------------------------------------------------------


class TestTaskCompletedHookSidecarAware:
    """Verify TaskCompleted hooks read sidecar progress file."""

    def test_medium_task_completed_reads_progress(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-task-completed.sh"]
        assert ".validation-progress.json" in script

    def test_medium_task_completed_ps_reads_progress(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_PS["tapps-task-completed.ps1"]
        assert ".validation-progress.json" in script

    def test_blocking_task_completed_reads_progress(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-task-completed.sh"]
        assert ".validation-progress.json" in script

    def test_blocking_task_completed_ps_reads_progress(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_BLOCKING_PS["tapps-task-completed.ps1"]
        assert ".validation-progress.json" in script

    def test_blocking_task_completed_shows_failed_files(self) -> None:
        """Blocking TaskCompleted hook lists individual failed files."""
        script = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-task-completed.sh"]
        assert "FAILED" in script

    def test_blocking_task_completed_ps_shows_failed_files(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_BLOCKING_PS["tapps-task-completed.ps1"]
        assert "FAILED" in script
