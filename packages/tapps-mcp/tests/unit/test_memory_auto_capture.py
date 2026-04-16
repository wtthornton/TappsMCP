"""Tests for memory auto-capture hook and runner (Epic 65.5)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.memory.auto_capture import run_auto_capture
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS_PS,
    MEMORY_AUTO_CAPTURE_HOOKS_CONFIG,
    MEMORY_AUTO_CAPTURE_HOOKS_CONFIG_PS,
)
from tapps_mcp.pipeline.platform_hooks import generate_memory_auto_capture_hook


class TestAutoCaptureRunner:
    """Tests for run_auto_capture."""

    def test_stop_hook_active_skips(self, tmp_path: Path) -> None:
        """When stop_hook_active is true, no extraction or save."""
        stdin = json.dumps({"stop_hook_active": True})
        result = run_auto_capture(stdin, tmp_path)
        assert result["saved"] == 0
        assert result["extracted_keys"] == []

    def test_short_context_skips(self, tmp_path: Path) -> None:
        """Context shorter than min_context_length skips."""
        stdin = json.dumps({"context": "short"})
        result = run_auto_capture(stdin, tmp_path, min_context_length=100)
        assert result["saved"] == 0

    def test_extracts_and_saves(self, tmp_path: Path) -> None:
        """Extracts durable facts and saves to store."""
        ctx = "We decided to use PostgreSQL for the database."
        stdin = json.dumps({"transcript": ctx})
        result = run_auto_capture(stdin, tmp_path, min_context_length=10)
        assert result["saved"] >= 1
        assert result["extracted_keys"]
        # Note: v3 (ADR-007) removed SQLite; no memory.db file is written.

    def test_transcript_field_used(self, tmp_path: Path) -> None:
        """Transcript field is extracted from payload."""
        ctx = "A key decision was to use Redis for caching."
        stdin = json.dumps({"transcript": ctx})
        result = run_auto_capture(stdin, tmp_path, min_context_length=10)
        assert result["saved"] >= 1

    def test_messages_field_used(self, tmp_path: Path) -> None:
        """Messages field is extracted from payload."""
        ctx = "We agreed on using ruff for linting across the project."
        stdin = json.dumps({
            "messages": [
                {"content": ctx},
            ],
        })
        result = run_auto_capture(stdin, tmp_path, min_context_length=10)
        assert result["saved"] >= 1

    def test_empty_extraction_no_save(self, tmp_path: Path) -> None:
        """No decision patterns -> no save."""
        stdin = json.dumps({"transcript": "We ran tests. All passed."})
        result = run_auto_capture(stdin, tmp_path, min_context_length=10)
        assert result["saved"] == 0


class TestAutoCaptureHookTemplate:
    """Verify the auto-capture hook script templates."""

    def test_bash_script_exists(self) -> None:
        assert "tapps-memory-auto-capture.sh" in CLAUDE_HOOK_SCRIPTS

    def test_bash_script_has_stop_hook_active_guard(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-memory-auto-capture.sh"]
        assert "stop_hook_active" in script

    def test_bash_script_invokes_auto_capture(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS["tapps-memory-auto-capture.sh"]
        assert "auto-capture" in script
        assert "tapps-mcp" in script

    def test_ps_script_exists(self) -> None:
        assert "tapps-memory-auto-capture.ps1" in CLAUDE_HOOK_SCRIPTS_PS

    def test_ps_script_has_stop_hook_active_guard(self) -> None:
        script = CLAUDE_HOOK_SCRIPTS_PS["tapps-memory-auto-capture.ps1"]
        assert "stop_hook_active" in script


class TestAutoCaptureHookConfig:
    """Verify the auto-capture hooks config."""

    def test_config_has_stop_event(self) -> None:
        assert "Stop" in MEMORY_AUTO_CAPTURE_HOOKS_CONFIG

    def test_config_ps_has_stop_event(self) -> None:
        assert "Stop" in MEMORY_AUTO_CAPTURE_HOOKS_CONFIG_PS

    def test_config_references_script(self) -> None:
        stop = MEMORY_AUTO_CAPTURE_HOOKS_CONFIG["Stop"]
        cmds = [h["command"] for e in stop for h in e.get("hooks", [])]
        assert any("tapps-memory-auto-capture.sh" in c for c in cmds)


class TestGenerateMemoryAutoCaptureHook:
    """Tests for generate_memory_auto_capture_hook."""

    def test_creates_bash_on_unix(self, tmp_path: Path) -> None:
        result = generate_memory_auto_capture_hook(tmp_path, force_windows=False)
        assert "tapps-memory-auto-capture.sh" in result["script_created"]
        assert (tmp_path / ".claude" / "hooks" / "tapps-memory-auto-capture.sh").exists()

    def test_creates_ps_on_windows(self, tmp_path: Path) -> None:
        result = generate_memory_auto_capture_hook(tmp_path, force_windows=True)
        assert "tapps-memory-auto-capture.ps1" in result["script_created"]
        assert (tmp_path / ".claude" / "hooks" / "tapps-memory-auto-capture.ps1").exists()

    def test_merges_stop_hook_into_settings(self, tmp_path: Path) -> None:
        generate_memory_auto_capture_hook(tmp_path, force_windows=False)
        settings = tmp_path / ".claude" / "settings.json"
        assert settings.exists()
        data = json.loads(settings.read_text())
        assert "hooks" in data
        assert "Stop" in data["hooks"]
        stop_commands = [
            h.get("command", "")
            for e in data["hooks"]["Stop"]
            for h in e.get("hooks", [e])
        ]
        assert any("tapps-memory-auto-capture" in c for c in stop_commands)
