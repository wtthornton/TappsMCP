"""Guard this repo's deployed ``.claude/settings.json`` hook wiring.

Two regressions this locks down:

* The PreToolUse/Bash destructive-command guard must wire the fail-*closed*
  ``tapps-pre-bash.sh`` (TAP-1785), not the retired fail-*open*
  ``tapps-pre-tooluse.sh``. The old hook had no ``[ -z "$PYBIN" ]`` guard, so a
  missing python interpreter let ``rm -rf`` through (exit 0). The generator
  moved to ``tapps-pre-bash.sh`` long ago; this asserts the deployed settings
  followed.
* The Stop event must not wire ``tapps-memory-capture.sh`` — a no-op since
  session capture went brain-native (``memory_index_session``, TAP-1999).
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def _hook_commands(settings: dict[str, object], event: str) -> list[str]:
    """Return every hook ``command`` string registered under *event*."""
    commands: list[str] = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    for entry in hooks.get(event, []) or []:
        for hook in entry.get("hooks", []) or []:
            cmd = hook.get("command")
            if isinstance(cmd, str):
                commands.append(cmd)
    return commands


def _load_settings() -> dict[str, object]:
    data: dict[str, object] = json.loads(SETTINGS.read_text(encoding="utf-8"))
    return data


def test_bash_guard_is_fail_closed_pre_bash() -> None:
    """The Bash PreToolUse guard wires the fail-closed hook, not the retired one."""
    settings = _load_settings()
    pre_tool = _hook_commands(settings, "PreToolUse")
    assert any("tapps-pre-bash.sh" in c for c in pre_tool), (
        "PreToolUse must wire the fail-closed tapps-pre-bash.sh destructive guard"
    )
    assert not any("tapps-pre-tooluse.sh" in c for c in pre_tool), (
        "tapps-pre-tooluse.sh is the retired fail-open guard — must not be wired"
    )


def test_retired_pre_tooluse_hook_is_deleted() -> None:
    """The retired fail-open hook file must not exist in the deployed hooks dir."""
    assert not (REPO_ROOT / ".claude" / "hooks" / "tapps-pre-tooluse.sh").exists()


def test_dead_memory_capture_hook_not_wired() -> None:
    """The no-op TAP-1999 memory-capture hook must not be wired into Stop."""
    settings = _load_settings()
    stop = _hook_commands(settings, "Stop")
    assert not any("tapps-memory-capture.sh" in c for c in stop), (
        "tapps-memory-capture.sh is a no-op (session capture is brain-native "
        "via memory_index_session, TAP-1999) — must not be wired"
    )
    assert not (REPO_ROOT / ".claude" / "hooks" / "tapps-memory-capture.sh").exists()
