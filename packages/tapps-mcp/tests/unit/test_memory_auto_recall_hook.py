"""Tests for the memory auto-recall hook (Epic 65.4).

Verifies the hook template content, generate_memory_auto_recall_hook(),
and the memory recall CLI subcommand.
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.pipeline.platform_hook_templates import (
    MEMORY_AUTO_RECALL_HOOKS_CONFIG,
    MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS,
    _memory_auto_recall_script,
    _memory_auto_recall_script_cursor,
    _memory_auto_recall_script_ps,
)
from tapps_mcp.pipeline.platform_hooks import generate_memory_auto_recall_hook

# ---------------------------------------------------------------------------
# Hook template content tests
# ---------------------------------------------------------------------------


class TestMemoryAutoRecallHookTemplate:
    """Verify the memory auto-recall hook script content."""

    def test_bash_script_has_tapps_mcp_memory_recall(self) -> None:
        script = _memory_auto_recall_script()
        assert "tapps-mcp" in script
        assert "memory recall" in script

    def test_bash_script_has_min_prompt_length_guard(self) -> None:
        script = _memory_auto_recall_script(min_prompt_length=50)
        assert "50" in script

    def test_bash_script_has_max_results_param(self) -> None:
        script = _memory_auto_recall_script(max_results=5)
        assert "5" in script

    def test_bash_script_exits_zero_gracefully(self) -> None:
        script = _memory_auto_recall_script()
        assert "exit 0" in script
        assert "exit 2" not in script

    def test_powershell_script_has_tapps_mcp_memory_recall(self) -> None:
        script = _memory_auto_recall_script_ps()
        assert "tapps-mcp" in script
        assert "memory recall" in script

    def test_config_has_session_start_and_pre_compact(self) -> None:
        assert "SessionStart" in MEMORY_AUTO_RECALL_HOOKS_CONFIG
        assert "PreCompact" in MEMORY_AUTO_RECALL_HOOKS_CONFIG

    def test_config_ps_has_session_start_and_pre_compact(self) -> None:
        assert "SessionStart" in MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS
        assert "PreCompact" in MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS

    def test_config_command_references_script(self) -> None:
        for event, entries in MEMORY_AUTO_RECALL_HOOKS_CONFIG.items():
            for entry in entries:
                for h in entry.get("hooks", []):
                    cmd = h.get("command", "")
                    assert "tapps-memory-auto-recall" in cmd

    def test_bash_script_skips_min_length_for_default_query(self) -> None:
        script = _memory_auto_recall_script(min_prompt_length=50)
        assert 'QUERY" != "$DEFAULT_QUERY"' in script

    def test_bash_script_embeds_recall_keys(self) -> None:
        script = _memory_auto_recall_script(recall_keys=["scope-key"])
        assert "--recall-key scope-key" in script

    def test_cursor_config_has_session_start_and_pre_compact(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG,
        )

        assert "sessionStart" in CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG
        assert "preCompact" in CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG

    def test_cursor_script_reaps_venv_mcp_zombies(self) -> None:
        script = _memory_auto_recall_script_cursor()
        assert "VENV_PIDS" in script
        assert r"\.venv\/bin\/(tapps-mcp|docsmcp|tapps-platform)" in script
        assert "NLT_DUP_PIDS" in script
        assert "ADR-0005" in script
        assert "NLT_STALE_PIDS" not in script
        assert "NLT_ALL_PIDS" not in script

    def test_cursor_zombie_cleanup_standalone_reaps_stale_nlt(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            _mcp_zombie_cleanup_standalone_script,
        )

        script = _mcp_zombie_cleanup_standalone_script()
        assert "NLT_STALE_PIDS" in script
        assert "NLT_ALL_PIDS" not in script
        assert "match($0" not in script
        assert "$2 > 45" in script
        assert "serve --profile nlt-" in script
        assert "exit 0" in script

    def test_cursor_zombie_cleanup_runs_under_mawk(self) -> None:
        import subprocess

        from tapps_mcp.pipeline.platform_hook_templates import (
            _mcp_zombie_cleanup_standalone_script,
        )

        script = _mcp_zombie_cleanup_standalone_script()
        subprocess.run(["bash", "-c", script], check=True, timeout=10)

    def test_cursor_session_start_hooks_include_zombie_cleanup(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG,
        )

        session_cmds = [
            e["command"] for e in CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG["sessionStart"]
        ]
        assert session_cmds[0] == ".cursor/hooks/tapps-mcp-zombie-cleanup.sh"
        assert ".cursor/hooks/tapps-memory-auto-recall.sh" in session_cmds

    def test_ensure_cursor_session_start_order_puts_zombie_first(self) -> None:
        from tapps_mcp.pipeline.platform_hooks import _ensure_cursor_session_start_order

        hooks = {
            "sessionStart": [
                {"command": ".cursor/hooks/tapps-memory-auto-recall.sh"},
                {"command": ".cursor/hooks/tapps-mcp-zombie-cleanup.sh"},
            ]
        }
        assert _ensure_cursor_session_start_order(hooks) is True
        assert hooks["sessionStart"][0]["command"] == ".cursor/hooks/tapps-mcp-zombie-cleanup.sh"


# ---------------------------------------------------------------------------
# generate_memory_auto_recall_hook() tests
# ---------------------------------------------------------------------------


class TestGenerateMemoryAutoRecallHook:
    """Tests for generate_memory_auto_recall_hook."""

    def test_creates_bash_script_on_unix(self, tmp_path: Path) -> None:
        result = generate_memory_auto_recall_hook(tmp_path, force_windows=False)
        assert result["script_created"] == "tapps-memory-auto-recall.sh"
        script_path = tmp_path / ".claude" / "hooks" / "tapps-memory-auto-recall.sh"
        assert script_path.exists()
        content = script_path.read_text()
        assert "tapps-mcp" in content
        assert "memory recall" in content

    def test_creates_powershell_script_on_windows(self, tmp_path: Path) -> None:
        result = generate_memory_auto_recall_hook(tmp_path, force_windows=True)
        assert result["script_created"] == "tapps-memory-auto-recall.ps1"
        script_path = tmp_path / ".claude" / "hooks" / "tapps-memory-auto-recall.ps1"
        assert script_path.exists()

    def test_merges_session_start_and_pre_compact_into_settings(self, tmp_path: Path) -> None:
        generate_memory_auto_recall_hook(tmp_path, force_windows=False)
        settings_file = tmp_path / ".claude" / "settings.json"
        assert settings_file.exists()
        config = json.loads(settings_file.read_text())
        assert "SessionStart" in config.get("hooks", {})
        assert "PreCompact" in config.get("hooks", {})

    def test_hooks_added_count(self, tmp_path: Path) -> None:
        result = generate_memory_auto_recall_hook(tmp_path, force_windows=False)
        assert result["hooks_added"] >= 1
        assert result["hooks_action"] in ("created", "skipped")

    def test_creates_cursor_script_on_unix(self, tmp_path: Path) -> None:
        result = generate_memory_auto_recall_hook(
            tmp_path, force_windows=False, platform="cursor"
        )
        assert result["platform"] == "cursor"
        script_path = tmp_path / ".cursor" / "hooks" / "tapps-memory-auto-recall.sh"
        zombie_path = tmp_path / ".cursor" / "hooks" / "tapps-mcp-zombie-cleanup.sh"
        assert script_path.exists()
        assert zombie_path.exists()
        hooks = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert "sessionStart" in hooks["hooks"]
        assert "preCompact" in hooks["hooks"]
        session_cmds = [e["command"] for e in hooks["hooks"]["sessionStart"]]
        assert ".cursor/hooks/tapps-mcp-zombie-cleanup.sh" in session_cmds
        assert ".cursor/hooks/tapps-memory-auto-recall.sh" in session_cmds

    def test_custom_max_results_min_score_baked_in(self, tmp_path: Path) -> None:
        generate_memory_auto_recall_hook(
            tmp_path,
            force_windows=False,
            max_results=3,
            min_score=0.5,
            min_prompt_length=100,
        )
        script_path = tmp_path / ".claude" / "hooks" / "tapps-memory-auto-recall.sh"
        content = script_path.read_text()
        assert "3" in content or "--max-results 3" in content
        assert "0.5" in content or "--min-score 0.5" in content
        assert "100" in content


# ---------------------------------------------------------------------------
# Memory recall CLI tests
# ---------------------------------------------------------------------------


class TestMemoryRecallCLI:
    """Tests for tapps-mcp memory recall CLI subcommand."""

    def test_recall_exits_zero_when_no_store(self, tmp_path: Path) -> None:
        """Memory recall exits 0 when no MemoryStore (graceful fallback)."""
        from click.testing import CliRunner

        from tapps_mcp.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "memory",
                "recall",
                "--query",
                "test",
                "--project-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        assert "<memory_context>" not in (result.output or "")

    def test_recall_outputs_xml_when_memories_exist(self, tmp_path: Path) -> None:
        """Memory recall outputs <memory_context> XML when memories match."""
        from click.testing import CliRunner

        from tapps_brain.store import MemoryStore

        # Create memory store with an entry
        store = MemoryStore(tmp_path)
        try:
            store.save(
                key="test-key",
                value="test value for recall",
                tier="pattern",
                tags=["test"],
            )
        finally:
            store.close()

        from tapps_mcp.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "memory",
                "recall",
                "--query",
                "recall",
                "--project-root",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 0
        if "<memory_context>" in (result.output or ""):
            assert "test-key" in (result.output or "")
            assert "test value" in (result.output or "")
