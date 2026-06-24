"""Upgrade migration + doctor detection for retired hooks.

Covers ``_migrate_retired_hooks`` (rename the fail-open destructive guard to its
fail-closed replacement, unwire the no-op memory-capture hook, delete the
retired pre-tooluse file) and ``check_retired_hooks`` (doctor drift report).

Settings ``hooks`` entries are merge-only on upgrade, so without this migration
an existing project that wired ``tapps-pre-tooluse.sh`` (fail-open) or the no-op
``tapps-memory-capture.sh`` keeps running them after the platform retired them.
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.distribution.doctor import check_retired_hooks
from tapps_mcp.pipeline.upgrade import _migrate_retired_hooks


def _write_settings(project_root: Path, hooks: dict[str, object]) -> Path:
    settings_dir = project_root / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    sf = settings_dir / "settings.json"
    sf.write_text(json.dumps({"hooks": hooks}, indent=2) + "\n", encoding="utf-8")
    return sf


def _commands(settings_file: Path, event: str) -> list[str]:
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    out: list[str] = []
    for entry in data.get("hooks", {}).get(event, []) or []:
        for hook in entry.get("hooks", []) or []:
            cmd = hook.get("command")
            if isinstance(cmd, str):
                out.append(cmd)
    return out


def test_pre_tooluse_renamed_in_place_to_pre_bash(tmp_path: Path) -> None:
    """The Bash guard wiring is repointed to the fail-closed hook, not dropped."""
    sf = _write_settings(
        tmp_path,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "bash .claude/hooks/tapps-pre-tooluse.sh"}
                    ],
                }
            ]
        },
    )
    summary = _migrate_retired_hooks(tmp_path)

    pre_tool = _commands(sf, "PreToolUse")
    assert pre_tool == ["bash .claude/hooks/tapps-pre-bash.sh"]
    assert any("tapps-pre-tooluse.sh -> tapps-pre-bash.sh" in r for r in summary["renamed"])
    # The matcher entry survives — the guard is upgraded, never removed.
    data = json.loads(sf.read_text(encoding="utf-8"))
    assert data["hooks"]["PreToolUse"][0]["matcher"] == "Bash"


def test_memory_capture_unwired_and_empty_event_dropped(tmp_path: Path) -> None:
    """The no-op memory-capture Stop hook is unwired; siblings are preserved."""
    sf = _write_settings(
        tmp_path,
        {
            "Stop": [
                {"hooks": [{"type": "command", "command": "bash .claude/hooks/tapps-stop.sh"}]},
                {
                    "hooks": [
                        {"type": "command", "command": "bash .claude/hooks/tapps-memory-capture.sh"}
                    ]
                },
            ]
        },
    )
    summary = _migrate_retired_hooks(tmp_path)

    stop = _commands(sf, "Stop")
    assert "bash .claude/hooks/tapps-stop.sh" in stop
    assert not any("tapps-memory-capture.sh" in c for c in stop)
    assert "tapps-memory-capture.sh" in summary["unwired"]


def test_retired_pre_tooluse_file_deleted(tmp_path: Path) -> None:
    """The retired pre-tooluse script file is removed (no longer shipped)."""
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "tapps-pre-tooluse.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    _write_settings(tmp_path, {})

    summary = _migrate_retired_hooks(tmp_path)

    assert not (hooks_dir / "tapps-pre-tooluse.sh").exists()
    assert "tapps-pre-tooluse.sh" in summary["removed_files"]


def test_migration_is_noop_when_nothing_retired(tmp_path: Path) -> None:
    """A clean project is untouched and reports an empty summary."""
    sf = _write_settings(
        tmp_path,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "bash .claude/hooks/tapps-pre-bash.sh"}
                    ],
                }
            ]
        },
    )
    before = sf.read_text(encoding="utf-8")
    summary = _migrate_retired_hooks(tmp_path)

    assert summary == {"renamed": [], "unwired": [], "removed_files": []}
    assert sf.read_text(encoding="utf-8") == before


def test_doctor_flags_wired_memory_capture(tmp_path: Path) -> None:
    _write_settings(
        tmp_path,
        {
            "Stop": [
                {
                    "hooks": [
                        {"type": "command", "command": "bash .claude/hooks/tapps-memory-capture.sh"}
                    ]
                }
            ]
        },
    )
    result = check_retired_hooks(tmp_path)
    assert result.ok is False
    assert "memory-capture" in result.message
    assert "upgrade" in result.detail


def test_doctor_flags_present_pre_tooluse_file(tmp_path: Path) -> None:
    hooks_dir = tmp_path / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "tapps-pre-tooluse.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
    result = check_retired_hooks(tmp_path)
    assert result.ok is False
    assert "tapps-pre-tooluse.sh" in result.message


def test_doctor_passes_clean_project(tmp_path: Path) -> None:
    _write_settings(
        tmp_path,
        {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "bash .claude/hooks/tapps-pre-bash.sh"}
                    ],
                }
            ]
        },
    )
    result = check_retired_hooks(tmp_path)
    assert result.ok is True
