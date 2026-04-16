"""Tests for the memory-capture Stop hook (Epic 34.5).

Verifies the hook template content, the generate_memory_capture_hook()
function, the session capture processing in tapps_session_start, and
the memory_capture parameter in tapps_init / bootstrap_pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS_PS,
    MEMORY_CAPTURE_HOOKS_CONFIG,
    MEMORY_CAPTURE_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hooks import generate_memory_capture_hook

# ---------------------------------------------------------------------------
# Hook template content tests
# ---------------------------------------------------------------------------


class TestMemoryCaptureHookTemplate:
    """Verify the bash hook script content is valid and correct."""

    def test_bash_script_starts_with_shebang(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-memory-capture.sh"]
        assert script.startswith("#!/usr/bin/env bash")

    def test_bash_script_has_stop_hook_active_guard(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-memory-capture.sh"]
        assert "stop_hook_active" in script

    def test_bash_script_exits_zero_on_active(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-memory-capture.sh"]
        assert "exit 0" in script
        # Should NOT block (no exit 2)
        assert "exit 2" not in script

    def test_bash_script_writes_session_capture_json(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-memory-capture.sh"]
        assert "session-capture.json" in script

    def test_bash_script_checks_validation_marker(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-memory-capture.sh"]
        assert ".validation-marker" in script

    def test_bash_script_uses_claude_project_dir(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-memory-capture.sh"]
        assert "CLAUDE_PROJECT_DIR" in script

    def test_powershell_script_has_stop_hook_active_guard(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_PS["tapps-memory-capture.ps1"]
        assert "stop_hook_active" in script

    def test_powershell_script_writes_session_capture_json(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_PS["tapps-memory-capture.ps1"]
        assert "session-capture.json" in script


# ---------------------------------------------------------------------------
# Hook config tests
# ---------------------------------------------------------------------------


class TestMemoryCaptureHookConfig:
    """Verify the hooks config dicts are well-formed."""

    def test_config_has_stop_event(self) -> None:
        assert "Stop" in MEMORY_CAPTURE_HOOKS_CONFIG

    def test_config_ps_has_stop_event(self) -> None:
        assert "Stop" in MEMORY_CAPTURE_HOOKS_CONFIG_PS

    def test_config_command_references_script(self) -> None:
        entries = MEMORY_CAPTURE_HOOKS_CONFIG["Stop"]
        commands = [h["command"] for e in entries for h in e.get("hooks", [])]
        assert any("tapps-memory-capture" in c for c in commands)


# ---------------------------------------------------------------------------
# generate_memory_capture_hook() tests
# ---------------------------------------------------------------------------


class TestGenerateMemoryCaptureHook:
    """Tests for the generate_memory_capture_hook function."""

    def test_creates_bash_script_on_unix(self, tmp_path: Path) -> None:
        result = generate_memory_capture_hook(tmp_path, force_windows=False)
        assert result["script_created"] == "tapps-memory-capture.sh"
        script_path = tmp_path / ".claude" / "hooks" / "tapps-memory-capture.sh"
        assert script_path.exists()
        content = script_path.read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_creates_powershell_script_on_windows(self, tmp_path: Path) -> None:
        result = generate_memory_capture_hook(tmp_path, force_windows=True)
        assert result["script_created"] == "tapps-memory-capture.ps1"
        script_path = tmp_path / ".claude" / "hooks" / "tapps-memory-capture.ps1"
        assert script_path.exists()

    def test_merges_stop_hook_into_settings(self, tmp_path: Path) -> None:
        generate_memory_capture_hook(tmp_path, force_windows=False)
        settings_file = tmp_path / ".claude" / "settings.json"
        assert settings_file.exists()
        config = json.loads(settings_file.read_text())
        assert "Stop" in config.get("hooks", {})

    def test_does_not_duplicate_on_rerun(self, tmp_path: Path) -> None:
        generate_memory_capture_hook(tmp_path, force_windows=False)
        result2 = generate_memory_capture_hook(tmp_path, force_windows=False)
        assert result2["hooks_action"] == "skipped"
        assert result2["hooks_added"] == 0

    def test_hooks_added_count(self, tmp_path: Path) -> None:
        result = generate_memory_capture_hook(tmp_path, force_windows=False)
        assert result["hooks_added"] >= 1
        assert result["hooks_action"] == "created"


# ---------------------------------------------------------------------------
# memory_capture=False means no hook generated (via bootstrap_pipeline)
# ---------------------------------------------------------------------------


class TestMemoryCaptureInitParam:
    """Verify that memory_capture=False (default) does not generate hook."""

    def test_no_hook_when_memory_capture_false(self, tmp_path: Path) -> None:
        """bootstrap_pipeline with memory_capture=False should not create hook."""
        from tapps_mcp.pipeline.init import BootstrapConfig, bootstrap_pipeline

        cfg = BootstrapConfig(
            platform="claude",
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
            memory_capture=False,
        )
        result = bootstrap_pipeline(tmp_path, config=cfg)
        assert "memory_capture" not in result

    def test_default_memory_capture_is_false(self) -> None:
        from tapps_mcp.pipeline.init import BootstrapConfig

        cfg = BootstrapConfig()
        assert cfg.memory_capture is False


# ---------------------------------------------------------------------------
# Session capture processing tests
# ---------------------------------------------------------------------------


class TestProcessSessionCapture:
    """Tests for _process_session_capture in server_pipeline_tools."""

    def test_returns_none_when_no_capture_file(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _process_session_capture

        store = MagicMock()
        result = _process_session_capture(tmp_path, store)
        assert result is None

    def test_processes_capture_file(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _process_session_capture

        capture_dir = tmp_path / ".tapps-mcp"
        capture_dir.mkdir(parents=True)
        capture_data = {"date": "2026-03-01", "validated": True, "files_edited": 3}
        (capture_dir / "session-capture.json").write_text(
            json.dumps(capture_data), encoding="utf-8"
        )

        store = MagicMock()
        store.save.return_value = MagicMock()

        result = _process_session_capture(tmp_path, store)

        assert result is not None
        assert result["date"] == "2026-03-01"
        assert result["validated"] is True
        assert result["files_edited"] == 3

    def test_saves_to_memory_store(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _process_session_capture

        capture_dir = tmp_path / ".tapps-mcp"
        capture_dir.mkdir(parents=True)
        capture_data = {"date": "2026-03-01", "validated": False, "files_edited": 1}
        (capture_dir / "session-capture.json").write_text(
            json.dumps(capture_data), encoding="utf-8"
        )

        store = MagicMock()
        store.save.return_value = MagicMock()

        _process_session_capture(tmp_path, store)

        store.save.assert_called_once()
        call_kwargs = store.save.call_args
        assert call_kwargs[1]["key"] == "session-capture.2026-03-01"
        assert call_kwargs[1]["tier"] == "context"
        assert call_kwargs[1]["source"] == "system"
        assert "session-capture" in call_kwargs[1]["tags"]

    def test_deletes_capture_file_after_processing(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _process_session_capture

        capture_dir = tmp_path / ".tapps-mcp"
        capture_dir.mkdir(parents=True)
        capture_file = capture_dir / "session-capture.json"
        capture_file.write_text(
            json.dumps({"date": "2026-03-01", "validated": True, "files_edited": 0}),
            encoding="utf-8",
        )

        store = MagicMock()
        store.save.return_value = MagicMock()

        _process_session_capture(tmp_path, store)

        assert not capture_file.exists()

    def test_handles_malformed_json_gracefully(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _process_session_capture

        capture_dir = tmp_path / ".tapps-mcp"
        capture_dir.mkdir(parents=True)
        capture_file = capture_dir / "session-capture.json"
        capture_file.write_text("not valid json", encoding="utf-8")

        store = MagicMock()
        result = _process_session_capture(tmp_path, store)

        assert result is None
        store.save.assert_not_called()
        # File should be cleaned up even on failure
        assert not capture_file.exists()
