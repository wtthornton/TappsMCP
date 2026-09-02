"""Canonical hook manifest and retired-hook migration for the upgrade pipeline.

Extracted from :mod:`tapps_mcp.pipeline.upgrade` (TAP-6913).

Settings ``hooks`` entries are merge-only on upgrade (existing entries are
preserved, never removed), so a project that wired a hook before it was
superseded keeps running it forever unless upgrade actively migrates the
wiring. This module owns that migration plus the drift report against the
canonical manifest.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

from tapps_core.common.logging import get_logger

log = get_logger(__name__)

# TAP-1332: Canonical hook manifest. Every project upgraded with tapps_upgrade
# must end up with this exact set of `tapps-*` hook scripts under
# `.claude/hooks/`. Drift between projects (AgentForge vs external consumers on
# the same TappsMCP version) was caused by silent opt-in install paths; this
# manifest is authoritative for verification reporting.
CANONICAL_HOOK_MANIFEST: frozenset[str] = frozenset(
    {
        "tapps-session-start.sh",
        "tapps-session-compact.sh",
        "tapps-user-prompt-submit.sh",
        "tapps-pre-bash.sh",
        "tapps-pre-compact.sh",
        "tapps-post-edit.sh",
        "tapps-post-validate.sh",
        "tapps-post-report.sh",
        "tapps-post-docs-validate.sh",
        "tapps-post-linear-snapshot-get.sh",
        "tapps-post-linear-list.sh",
        "tapps-pre-linear-write.sh",
        "tapps-pre-linear-list.sh",
        "tapps-stop.sh",
        "tapps-task-completed.sh",
        "tapps-subagent-start.sh",
        "tapps-subagent-stop.sh",
        "tapps-memory-auto-capture.sh",
        # NOTE: tapps-session-end.sh and tapps-tool-failure.sh deploy ONLY at
        # engagement_level=high (SessionEnd / PostToolUseFailure events live in
        # ENGAGEMENT_HOOK_EVENTS["high"] only). They are intentionally omitted
        # from the canonical manifest so medium/low projects don't false-positive.
    }
)

# Renames swap the command in place (matcher/structure preserved) so a safety
# guard is upgraded, never dropped.
RETIRED_HOOK_RENAMES: dict[str, str] = {
    # Fail-OPEN destructive guard -> fail-closed replacement (TAP-1785). The old
    # hook had no ``[ -z "$PYBIN" ]`` guard, so a missing interpreter let
    # destructive recursive-delete commands through (exit 0).
    "tapps-pre-tooluse.sh": "tapps-pre-bash.sh",
    "tapps-pre-tooluse.ps1": "tapps-pre-bash.ps1",
}
# No-op hooks to unwire (session capture went brain-native via
# ``memory_index_session``, TAP-1999). memory-capture is fully retired — its
# template, generator, and tapps_init opt-in were removed — so the wiring is
# stripped AND the file is deleted (see ``RETIRED_HOOK_DELETE``).
RETIRED_HOOK_UNWIRE: frozenset[str] = frozenset(
    {"tapps-memory-capture.sh", "tapps-memory-capture.ps1"}
)
# Retired hook *files* no longer shipped by canonical generation — safe to
# delete outright. tapps-pre-tooluse is renamed (its wiring repoints to the
# fail-closed replacement, which canonical generation ships); memory-capture is
# gone entirely.
RETIRED_HOOK_DELETE: frozenset[str] = frozenset(
    {
        "tapps-pre-tooluse.sh",
        "tapps-pre-tooluse.ps1",
        "tapps-memory-capture.sh",
        "tapps-memory-capture.ps1",
    }
)

_MANAGED_HOOK_FILENAME = re.compile(r"^tapps-[a-z0-9-]+\.(sh|ps1)$")


def is_managed_hook_filename(name: str) -> bool:
    """True for live tapps hook scripts, not co-located ``.pre-upgrade.*`` sidecars."""
    if ".pre-upgrade." in name:
        return False
    return bool(_MANAGED_HOOK_FILENAME.match(name))


def verify_hook_manifest(project_root: Path) -> dict[str, Any]:
    """TAP-1332: report missing/stale hooks against the canonical manifest.

    Returns a structured report (always populated; never raises). Used by the
    claude-code live upgrade to surface drift in the upgrade result so
    operators can see at a glance whether their project matches the platform
    contract. ``stale`` entries are scripts older than the tapps-mcp module
    file by ``mtime`` — a heuristic for "this hook predates a template
    update and should be re-deployed".
    """
    hooks_dir = project_root / ".claude" / "hooks"
    if not hooks_dir.is_dir():
        return {
            "ok": False,
            "missing": sorted(CANONICAL_HOOK_MANIFEST),
            "extra": [],
            "stale": [],
            "hint": (
                "Run tapps_upgrade with destructive_guard / linear_enforce_gate "
                "flags appropriate to the project."
            ),
        }
    present = {p.name for p in hooks_dir.glob("tapps-*.sh") if p.is_file()}
    missing = sorted(CANONICAL_HOOK_MANIFEST - present)
    extra = sorted(present - CANONICAL_HOOK_MANIFEST)
    return {
        "ok": not missing,
        "missing": missing,
        "extra": extra,
        "stale": [],
        "manifest_size": len(CANONICAL_HOOK_MANIFEST),
        "deployed_size": len(present),
    }


def _migrate_inner_hook(inner: Any, summary: dict[str, Any]) -> bool:
    """Rewrite one inner hook entry in place.

    Returns ``True`` when the entry should be kept, ``False`` when it wires a
    retired no-op hook and must be dropped. ``summary`` accumulates the
    rename/unwire report.
    """
    cmd = inner.get("command") if isinstance(inner, dict) else None
    if not isinstance(cmd, str):
        return True
    for old, new in RETIRED_HOOK_RENAMES.items():
        if old in cmd:
            inner["command"] = cmd.replace(old, new)
            cmd = inner["command"]
            summary["renamed"].append(f"{old} -> {new}")
    unwired = next((n for n in RETIRED_HOOK_UNWIRE if n in cmd), None)
    if unwired is None:
        return True
    summary["unwired"].append(unwired)
    return False


def _migrate_hook_entries(entries: list[Any], summary: dict[str, Any]) -> list[Any]:
    """Rewrite one event's matcher entries, dropping those left with no hooks."""
    new_entries: list[Any] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
            new_entries.append(entry)
            continue
        kept_inner = [inner for inner in entry["hooks"] if _migrate_inner_hook(inner, summary)]
        if kept_inner:
            entry["hooks"] = kept_inner
            new_entries.append(entry)
    return new_entries


def _rewrite_settings_hooks(hooks: dict[str, Any], summary: dict[str, Any]) -> None:
    """Apply the retired-hook rewrites to one settings file's ``hooks`` block."""
    for event in list(hooks.keys()):
        entries = hooks.get(event)
        if not isinstance(entries, list):
            continue
        new_entries = _migrate_hook_entries(entries, summary)
        if new_entries:
            hooks[event] = new_entries
        else:
            del hooks[event]


def _migrate_settings_file(settings_file: Path, summary: dict[str, Any]) -> None:
    """Migrate one Claude settings file, writing it back only when it changed.

    An entry is dropped (and an event deleted) only when every inner hook it
    held was unwired, so "the summary grew" is an exact stand-in for "the
    config changed".
    """
    from tapps_mcp.pipeline.platform_hooks import (
        ManagedJsonError,
        _load_managed_json,
        _write_managed_json,
    )

    try:
        config = _load_managed_json(settings_file)
    except ManagedJsonError:
        return
    hooks = config.get("hooks")
    if not isinstance(hooks, dict):
        return

    before = (len(summary["renamed"]), len(summary["unwired"]))
    _rewrite_settings_hooks(hooks, summary)
    if (len(summary["renamed"]), len(summary["unwired"])) != before:
        with contextlib.suppress(OSError):  # disk errors are non-fatal here
            _write_managed_json(settings_file, config)


def _delete_retired_hook_files(project_root: Path, summary: dict[str, Any]) -> None:
    """Unlink retired hook scripts canonical generation no longer ships."""
    hooks_dir = project_root / ".claude" / "hooks"
    for name in sorted(RETIRED_HOOK_DELETE):
        retired_file = hooks_dir / name
        if not retired_file.is_file():
            continue
        try:
            retired_file.unlink()
            summary["removed_files"].append(name)
        except OSError:  # pragma: no cover - disk error
            pass


def migrate_retired_hooks(project_root: Path) -> dict[str, Any]:
    """Rewire/strip retired hooks in an existing project's Claude settings.

    * Renames a retired hook's command in place to its fail-closed replacement
      (``tapps-pre-tooluse.sh`` -> ``tapps-pre-bash.sh``) so the destructive
      guard is upgraded rather than silently dropped.
    * Drops the wiring for pure no-op hooks (``tapps-memory-capture.sh``).
    * Deletes retired hook script files canonical generation no longer ships.

    Always returns a summary; never raises into the upgrade flow.
    """
    summary: dict[str, Any] = {"renamed": [], "unwired": [], "removed_files": []}

    for settings_name in ("settings.json", "settings.local.json"):
        settings_file = project_root / ".claude" / settings_name
        if settings_file.exists():
            _migrate_settings_file(settings_file, summary)

    _delete_retired_hook_files(project_root, summary)
    return summary
