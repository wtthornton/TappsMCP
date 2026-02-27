"""Tests for Epic 18: MCP Upgrade Tool + Exe Path Handling."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.distribution.doctor import (
    check_binary_on_path,
    check_json_config,
    run_doctor_structured,
)
from tapps_mcp.distribution.setup_generator import (
    _build_server_entry,
    _detect_command_path,
    _is_valid_tapps_command,
    _merge_config,
    _validate_config_file,
)


# ---------------------------------------------------------------------------
# Story 2: _detect_command_path tests
# ---------------------------------------------------------------------------


class TestDetectCommandPath:
    """Tests for auto-detection of the tapps-mcp command path."""

    def test_frozen_exe_returns_sys_executable(self) -> None:
        """When running as a frozen exe, returns sys.executable."""
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", r"C:\Users\test\.local\bin\tapps-mcp.exe"),
        ):
            result = _detect_command_path()
        assert result == r"C:\Users\test\.local\bin\tapps-mcp.exe"

    def test_on_path_returns_bare_name(self) -> None:
        """When tapps-mcp is on PATH, returns 'tapps-mcp'."""
        with (
            patch.object(sys, "frozen", False, create=True),
            patch("tapps_mcp.distribution.setup_generator.shutil.which", return_value="/usr/bin/tapps-mcp"),
        ):
            result = _detect_command_path()
        assert result == "tapps-mcp"

    def test_fallback_returns_bare_name(self) -> None:
        """When neither frozen nor on PATH, returns 'tapps-mcp'."""
        with (
            patch.object(sys, "frozen", False, create=True),
            patch("tapps_mcp.distribution.setup_generator.shutil.which", return_value=None),
        ):
            result = _detect_command_path()
        assert result == "tapps-mcp"

    def test_build_server_entry_uses_detected_path(self) -> None:
        """_build_server_entry uses _detect_command_path for the command."""
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", r"C:\custom\tapps-mcp.exe"),
        ):
            entry = _build_server_entry("cursor")
        assert entry["command"] == r"C:\custom\tapps-mcp.exe"
        assert entry["args"] == ["serve"]

    def test_build_server_entry_adds_instructions_for_claude(self) -> None:
        """Claude Code entry gets instructions field."""
        with patch(
            "tapps_mcp.distribution.setup_generator._detect_command_path",
            return_value="tapps-mcp",
        ):
            entry = _build_server_entry("claude-code")
        assert "instructions" in entry
        assert "quality" in entry["instructions"].lower()


# ---------------------------------------------------------------------------
# Story 3: _is_valid_tapps_command tests
# ---------------------------------------------------------------------------


class TestIsValidTappsCommand:
    """Tests for command path validation."""

    def test_bare_name(self) -> None:
        assert _is_valid_tapps_command("tapps-mcp") is True

    def test_exe_path_windows(self) -> None:
        assert _is_valid_tapps_command(r"C:\Users\test\.local\bin\tapps-mcp.exe") is True

    def test_exe_path_unix(self) -> None:
        assert _is_valid_tapps_command("/usr/local/bin/tapps-mcp") is True

    def test_exe_path_with_spaces(self) -> None:
        assert _is_valid_tapps_command(r"C:\Program Files\TappsMCP\tapps-mcp.exe") is True

    def test_wrong_command_name(self) -> None:
        assert _is_valid_tapps_command("python") is False

    def test_empty_string(self) -> None:
        assert _is_valid_tapps_command("") is False

    def test_similar_but_wrong_name(self) -> None:
        assert _is_valid_tapps_command("tapps-mcp-old") is False


# ---------------------------------------------------------------------------
# Story 1: upgrade_mode in _merge_config
# ---------------------------------------------------------------------------


class TestMergeConfigUpgradeMode:
    """Tests for command preservation during upgrade."""

    def test_upgrade_mode_preserves_custom_command(self) -> None:
        """upgrade_mode=True keeps existing command and args."""
        existing = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": r"C:\custom\tapps-mcp.exe",
                    "args": ["serve"],
                    "env": {"TAPPS_MCP_PROJECT_ROOT": "old"},
                },
            },
        }
        result = _merge_config(existing, "cursor", upgrade_mode=True)
        entry = result["mcpServers"]["tapps-mcp"]
        assert entry["command"] == r"C:\custom\tapps-mcp.exe"
        assert entry["args"] == ["serve"]
        # env should still be updated
        assert entry["env"]["TAPPS_MCP_PROJECT_ROOT"] == "${workspaceFolder}"

    def test_upgrade_mode_false_overwrites_command(self) -> None:
        """upgrade_mode=False (default) overwrites command."""
        existing = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": r"C:\custom\tapps-mcp.exe",
                    "args": ["serve"],
                },
            },
        }
        result = _merge_config(existing, "cursor", upgrade_mode=False)
        entry = result["mcpServers"]["tapps-mcp"]
        assert entry["command"] == "tapps-mcp"

    def test_upgrade_mode_no_existing_entry(self) -> None:
        """upgrade_mode=True with no existing entry uses detected path."""
        existing = {"mcpServers": {}}
        result = _merge_config(existing, "cursor", upgrade_mode=True)
        entry = result["mcpServers"]["tapps-mcp"]
        assert entry["command"] == "tapps-mcp"

    def test_upgrade_mode_preserves_custom_args(self) -> None:
        """upgrade_mode=True preserves custom args too."""
        existing = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "/opt/tapps-mcp",
                    "args": ["serve", "--port", "9000"],
                },
            },
        }
        result = _merge_config(existing, "cursor", upgrade_mode=True)
        entry = result["mcpServers"]["tapps-mcp"]
        assert entry["args"] == ["serve", "--port", "9000"]


# ---------------------------------------------------------------------------
# Story 3: _validate_config_file accepts exe paths
# ---------------------------------------------------------------------------


class TestValidateConfigFileExePaths:
    """Tests for config validation accepting custom exe paths."""

    def test_accepts_bare_name(self, tmp_path: Path) -> None:
        config = {"mcpServers": {"tapps-mcp": {"command": "tapps-mcp"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        assert _validate_config_file(path, "mcpServers") is None

    def test_accepts_exe_path(self, tmp_path: Path) -> None:
        config = {"mcpServers": {"tapps-mcp": {"command": r"C:\bin\tapps-mcp.exe"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        assert _validate_config_file(path, "mcpServers") is None

    def test_rejects_wrong_command(self, tmp_path: Path) -> None:
        config = {"mcpServers": {"tapps-mcp": {"command": "python"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        error = _validate_config_file(path, "mcpServers")
        assert error is not None
        assert "Unexpected command" in error


# ---------------------------------------------------------------------------
# Story 3: check_binary_on_path with frozen exe
# ---------------------------------------------------------------------------


class TestCheckBinaryFrozen:
    """Tests for binary check with PyInstaller frozen exe."""

    def test_frozen_exe_always_passes(self) -> None:
        """Frozen exe should pass even if not on PATH."""
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", r"C:\test\tapps-mcp.exe"),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            result = check_binary_on_path()
        assert result.ok is True
        assert "frozen" in result.message.lower()

    def test_not_frozen_falls_back_to_which(self) -> None:
        """Non-frozen checks PATH normally."""
        with (
            patch.object(sys, "frozen", False, create=True),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            result = check_binary_on_path()
        assert result.ok is False


# ---------------------------------------------------------------------------
# Story 3: doctor.py _validate_json_config accepts exe paths
# ---------------------------------------------------------------------------


class TestDoctorValidateJsonConfigExePaths:
    """Doctor's JSON validation should accept custom exe paths."""

    def test_accepts_exe_path(self, tmp_path: Path) -> None:
        config = {"mcpServers": {"tapps-mcp": {"command": r"C:\bin\tapps-mcp.exe"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is True

    def test_accepts_unix_path(self, tmp_path: Path) -> None:
        config = {"mcpServers": {"tapps-mcp": {"command": "/usr/local/bin/tapps-mcp"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is True

    def test_rejects_wrong_command(self, tmp_path: Path) -> None:
        config = {"mcpServers": {"tapps-mcp": {"command": "node"}}}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        result = check_json_config(path, "mcpServers", "Test")
        assert result.ok is False
        assert "Unexpected command" in result.message


# ---------------------------------------------------------------------------
# Story 5: run_doctor_structured
# ---------------------------------------------------------------------------


class TestRunDoctorStructured:
    """Tests for the structured doctor output."""

    def test_returns_structured_dict(self, tmp_path: Path) -> None:
        """run_doctor_structured returns a dict with expected keys."""
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            result = run_doctor_structured(project_root=str(tmp_path))
        assert "checks" in result
        assert "pass_count" in result
        assert "fail_count" in result
        assert "all_passed" in result
        assert isinstance(result["checks"], list)
        assert result["pass_count"] + result["fail_count"] == len(result["checks"])

    def test_all_passed_is_false_with_failures(self, tmp_path: Path) -> None:
        """all_passed is False when checks fail."""
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            result = run_doctor_structured(project_root=str(tmp_path))
        assert result["all_passed"] is False
        assert result["fail_count"] > 0

    def test_check_entries_have_required_fields(self, tmp_path: Path) -> None:
        """Each check entry has name, ok, and message."""
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            result = run_doctor_structured(project_root=str(tmp_path))
        for check in result["checks"]:
            assert "name" in check
            assert "ok" in check
            assert "message" in check

    def test_includes_llm_engagement_level_when_configured(self, tmp_path: Path) -> None:
        """When .tapps-mcp.yaml has llm_engagement_level, result includes it (Epic 18.8)."""
        (tmp_path / ".tapps-mcp.yaml").write_text("llm_engagement_level: high\n")
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            result = run_doctor_structured(project_root=str(tmp_path))
        assert result.get("llm_engagement_level") == "high"

    def test_omits_llm_engagement_level_without_config(self, tmp_path: Path) -> None:
        """When .tapps-mcp.yaml is absent, result has no llm_engagement_level key."""
        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
        ):
            result = run_doctor_structured(project_root=str(tmp_path))
        assert "llm_engagement_level" not in result


# ---------------------------------------------------------------------------
# Story 6: Non-blocking stop hook templates
# ---------------------------------------------------------------------------


class TestNonBlockingHookTemplates:
    """Verify hook templates use exit 0 instead of exit 2."""

    def test_stop_hook_exits_zero(self) -> None:
        """Stop hook template should use exit 0 (non-blocking)."""
        from tapps_mcp.pipeline.platform_generators import _CLAUDE_HOOK_SCRIPTS

        stop_script = _CLAUDE_HOOK_SCRIPTS["tapps-stop.sh"]
        assert "exit 2" not in stop_script
        # Should have exit 0 for the main path
        lines = stop_script.strip().split("\n")
        last_line = lines[-1].strip()
        assert last_line == "exit 0"

    def test_task_completed_hook_exits_zero(self) -> None:
        """Task completed hook template should use exit 0 (non-blocking)."""
        from tapps_mcp.pipeline.platform_generators import _CLAUDE_HOOK_SCRIPTS

        task_script = _CLAUDE_HOOK_SCRIPTS["tapps-task-completed.sh"]
        assert "exit 2" not in task_script
        lines = task_script.strip().split("\n")
        last_line = lines[-1].strip()
        assert last_line == "exit 0"

    def test_stop_hook_still_prints_reminder(self) -> None:
        """Stop hook should still print a reminder to stderr."""
        from tapps_mcp.pipeline.platform_generators import _CLAUDE_HOOK_SCRIPTS

        stop_script = _CLAUDE_HOOK_SCRIPTS["tapps-stop.sh"]
        assert "Reminder" in stop_script or "tapps_validate_changed" in stop_script


# ---------------------------------------------------------------------------
# Story 4: upgrade_pipeline
# ---------------------------------------------------------------------------


class TestUpgradePipeline:
    """Tests for the upgrade pipeline core function."""

    def test_creates_agents_md_when_missing(self, tmp_path: Path) -> None:
        """Upgrade creates AGENTS.md when it doesn't exist."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path)
        assert result["components"]["agents_md"]["action"] == "created"
        assert (tmp_path / "AGENTS.md").exists()

    def test_dry_run_does_not_create_files(self, tmp_path: Path) -> None:
        """Dry run reports what would change but doesn't write files."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path, dry_run=True)
        assert result["dry_run"] is True
        assert not (tmp_path / "AGENTS.md").exists()

    def test_agents_md_up_to_date(self, tmp_path: Path) -> None:
        """Reports up-to-date when AGENTS.md is current."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline
        from tapps_mcp.prompts.prompt_loader import load_agents_template

        (tmp_path / "AGENTS.md").write_text(load_agents_template(), encoding="utf-8")
        result = upgrade_pipeline(tmp_path)
        assert result["components"]["agents_md"]["action"] == "up-to-date"

    def test_detects_claude_platform(self, tmp_path: Path) -> None:
        """Detects Claude platform from .claude directory."""
        from tapps_mcp.pipeline.upgrade import _detect_platform

        (tmp_path / ".claude").mkdir()
        assert _detect_platform(tmp_path) == "claude"

    def test_detects_cursor_platform(self, tmp_path: Path) -> None:
        """Detects Cursor platform from .cursor directory."""
        from tapps_mcp.pipeline.upgrade import _detect_platform

        (tmp_path / ".cursor").mkdir()
        assert _detect_platform(tmp_path) == "cursor"

    def test_detects_both_platforms(self, tmp_path: Path) -> None:
        """Detects both platforms when both directories exist."""
        from tapps_mcp.pipeline.upgrade import _detect_platform

        (tmp_path / ".claude").mkdir()
        (tmp_path / ".cursor").mkdir()
        assert _detect_platform(tmp_path) == "both"

    def test_result_has_version(self, tmp_path: Path) -> None:
        """Result includes the TappsMCP version."""
        from tapps_mcp import __version__
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path)
        assert result["version"] == __version__

    def test_result_has_success_flag(self, tmp_path: Path) -> None:
        """Result includes success flag."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        result = upgrade_pipeline(tmp_path)
        assert "success" in result
        assert isinstance(result["success"], bool)


# ---------------------------------------------------------------------------
# Story 7: EXPECTED_TOOLS count
# ---------------------------------------------------------------------------


class TestExpectedToolsCount:
    """Verify tool counts match after adding tapps_upgrade and tapps_doctor."""

    def test_expected_tools_is_26(self) -> None:
        from tapps_mcp.pipeline.agents_md import EXPECTED_TOOLS

        assert len(EXPECTED_TOOLS) == 26

    def test_upgrade_in_expected_tools(self) -> None:
        from tapps_mcp.pipeline.agents_md import EXPECTED_TOOLS

        assert "tapps_upgrade" in EXPECTED_TOOLS

    def test_doctor_in_expected_tools(self) -> None:
        from tapps_mcp.pipeline.agents_md import EXPECTED_TOOLS

        assert "tapps_doctor" in EXPECTED_TOOLS
