"""Tests for the memory auto-recall hook (Epic 65.4).

Verifies the hook template content, generate_memory_auto_recall_hook(),
and the memory recall CLI subcommand.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from tapps_mcp.pipeline.platform_hook_templates import (
    MEMORY_AUTO_RECALL_HOOKS_CONFIG,
    MEMORY_AUTO_RECALL_HOOKS_CONFIG_PS,
    _memory_auto_recall_script,
    _memory_auto_recall_script_cursor,
    _memory_auto_recall_script_ps,
)
from tapps_mcp.pipeline.platform_hooks import (
    generate_memory_auto_recall_hook,
    wire_memory_hooks,
)

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

    def test_cursor_script_does_not_reap_mcp_on_session_start(self) -> None:
        script = _memory_auto_recall_script_cursor()
        assert "ORPHAN_PIDS" not in script
        assert "Reaping orphaned MCP serve PIDs" not in script
        assert "memory recall" in script

    def test_cursor_zombie_cleanup_standalone_is_deprecated_noop(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            _mcp_zombie_cleanup_standalone_script,
        )

        script = _mcp_zombie_cleanup_standalone_script()
        assert "DEPRECATED" in script
        assert "deploy-local" in script
        assert "exit 0" in script

    def test_cursor_zombie_cleanup_standalone_exits_zero(self) -> None:
        import subprocess

        from tapps_mcp.pipeline.platform_hook_templates import (
            _mcp_zombie_cleanup_standalone_script,
        )

        script = _mcp_zombie_cleanup_standalone_script()
        subprocess.run(["bash", "-c", script], check=True, timeout=10)

    def test_cursor_session_start_hooks_recall_only(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG,
        )

        session_cmds = [
            e["command"] for e in CURSOR_MEMORY_AUTO_RECALL_HOOKS_CONFIG["sessionStart"]
        ]
        assert session_cmds == [".cursor/hooks/tapps-memory-auto-recall.sh"]

    def test_ensure_cursor_session_start_order_strips_zombie(self) -> None:
        from tapps_mcp.pipeline.platform_hooks import _ensure_cursor_session_start_order

        hooks = {
            "sessionStart": [
                {"command": ".cursor/hooks/tapps-memory-auto-recall.sh"},
                {"command": ".cursor/hooks/tapps-mcp-zombie-cleanup.sh"},
            ]
        }
        assert _ensure_cursor_session_start_order(hooks) is True
        assert hooks["sessionStart"] == [
            {"command": ".cursor/hooks/tapps-memory-auto-recall.sh"},
        ]


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
        result = generate_memory_auto_recall_hook(tmp_path, force_windows=False, platform="cursor")
        assert result["platform"] == "cursor"
        script_path = tmp_path / ".cursor" / "hooks" / "tapps-memory-auto-recall.sh"
        zombie_path = tmp_path / ".cursor" / "hooks" / "tapps-mcp-zombie-cleanup.sh"
        assert script_path.exists()
        assert zombie_path.exists()
        hooks = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert "sessionStart" in hooks["hooks"]
        assert "preCompact" in hooks["hooks"]
        session_cmds = [e["command"] for e in hooks["hooks"]["sessionStart"]]
        assert ".cursor/hooks/tapps-mcp-zombie-cleanup.sh" not in session_cmds
        assert ".cursor/hooks/tapps-memory-auto-recall.sh" in session_cmds

    def test_cursor_memory_recall_migrates_ps1_on_unix(self, tmp_path: Path) -> None:
        """sessionStart must not keep both .ps1 and .sh memory-recall hooks (TAP-4080)."""
        from tapps_mcp.pipeline.platform_hook_templates import PS1_PREFIX
        from tapps_mcp.pipeline.platform_hooks import _generate_cursor_memory_auto_recall_hook

        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)
        ps1_cmd = PS1_PREFIX + ".cursor/hooks/tapps-memory-auto-recall.ps1"
        existing = {
            "version": 1,
            "hooks": {
                "sessionStart": [{"command": ps1_cmd}],
                "preCompact": [{"command": ps1_cmd}],
            },
        }
        (cursor_dir / "hooks.json").write_text(json.dumps(existing), encoding="utf-8")

        _generate_cursor_memory_auto_recall_hook(
            tmp_path,
            win=False,
            max_results=3,
            min_score=0.3,
            min_prompt_length=50,
            recall_keys=[],
        )

        hooks = json.loads((cursor_dir / "hooks.json").read_text())
        for event in ("sessionStart", "preCompact"):
            cmds = [e["command"] for e in hooks["hooks"][event]]
            assert len(cmds) == 1
            assert cmds[0] == ".cursor/hooks/tapps-memory-auto-recall.sh"
            assert ".ps1" not in cmds[0]

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


class TestWireMemoryHooksMinScoreThreading:
    """``.tapps-mcp.yaml``'s ``memory_hooks.auto_recall.min_score`` must reach the
    generated hook script's ``--min-score`` arg via ``wire_memory_hooks`` →
    ``generate_memory_auto_recall_hook`` — this is already wired (TAP-6701 anchor
    recon); this test only proves it, it does not re-plumb it.
    """

    def test_custom_min_score_in_tapps_mcp_yaml_reaches_generated_script(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "memory_hooks:\n  auto_recall:\n    enabled: true\n    min_score: 0.73\n",
            encoding="utf-8",
        )
        result = wire_memory_hooks(tmp_path, platform="claude")
        assert "memory_auto_recall" in result
        script_path = tmp_path / ".claude" / "hooks" / "tapps-memory-auto-recall.sh"
        content = script_path.read_text()
        assert "--min-score 0.73" in content

    def test_default_min_score_in_generated_script_when_unconfigured(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text(
            "memory_hooks:\n  auto_recall:\n    enabled: true\n", encoding="utf-8"
        )
        wire_memory_hooks(tmp_path, platform="claude")
        script_path = tmp_path / ".claude" / "hooks" / "tapps-memory-auto-recall.sh"
        content = script_path.read_text()
        assert "--min-score 0.3" in content


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

    @staticmethod
    def _recall_fixture_hits() -> list[dict[str, object]]:
        """A recorded ``/v1/recall``-shaped response: 3 hits, mixed wire ``score``."""
        return [
            {"key": "low-score", "tier": "pattern", "value": "low value", "score": 0.2},
            {"key": "mid-score", "tier": "pattern", "value": "mid value", "score": 0.5},
            {"key": "high-score", "tier": "pattern", "value": "high value", "score": 0.8},
        ]

    def test_recall_min_score_0_3_vs_0_9_filter_differently(self, tmp_path: Path) -> None:
        """VAL-21: filtering on wire ``score`` — 0.3 keeps mid/high, 0.9 keeps none."""
        from click.testing import CliRunner

        from tapps_mcp.cli import main

        bridge = AsyncMock()
        bridge.search = AsyncMock(return_value=self._recall_fixture_hits())
        bridge.get = AsyncMock(return_value=None)
        bridge.close = lambda: None
        runner = CliRunner()

        with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=bridge):
            low_threshold = runner.invoke(
                main,
                [
                    "memory",
                    "recall",
                    "--query",
                    "x",
                    "--project-root",
                    str(tmp_path),
                    "--min-score",
                    "0.3",
                ],
            )
            high_threshold = runner.invoke(
                main,
                [
                    "memory",
                    "recall",
                    "--query",
                    "x",
                    "--project-root",
                    str(tmp_path),
                    "--min-score",
                    "0.9",
                ],
            )

        assert low_threshold.exit_code == 0
        assert high_threshold.exit_code == 0
        assert "mid-score" in low_threshold.output
        assert "high-score" in low_threshold.output
        assert "low-score" not in low_threshold.output
        assert "<memory_context>" not in high_threshold.output
        assert low_threshold.output != high_threshold.output

    def test_recall_score_absent_hit_passed_through_unfiltered(self, tmp_path: Path) -> None:
        """A hit with no wire ``score`` key (older-brain response) is never dropped,
        and never falls back to reading ``confidence`` (the deleted TAP-6701 path)."""
        from click.testing import CliRunner

        from tapps_mcp.cli import main

        hits: list[dict[str, object]] = [
            {"key": "no-score", "tier": "pattern", "value": "unscored value"},
            {"key": "high-conf-no-score", "tier": "pattern", "value": "x", "confidence": 0.99},
        ]
        bridge = AsyncMock()
        bridge.search = AsyncMock(return_value=hits)
        bridge.get = AsyncMock(return_value=None)
        bridge.close = lambda: None
        runner = CliRunner()

        with patch("tapps_core.brain_bridge.create_brain_bridge", return_value=bridge):
            result = runner.invoke(
                main,
                [
                    "memory",
                    "recall",
                    "--query",
                    "x",
                    "--project-root",
                    str(tmp_path),
                    "--min-score",
                    "0.99",
                ],
            )

        assert result.exit_code == 0
        # Absent-score hits pass through regardless of --min-score, and are not
        # filtered by any fallback read of "confidence".
        assert "no-score" in result.output
        assert "high-conf-no-score" in result.output
