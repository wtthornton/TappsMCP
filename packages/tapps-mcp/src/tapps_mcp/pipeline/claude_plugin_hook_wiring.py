"""Hook wiring for the Claude Code plugin bundle (TAP-7754).

Two defects shipped on opposite sides of "the script exists", and the bundle's
own referential-integrity check saw neither.

**A shipped script nothing wires.** ``CLAUDE_HOOK_SCRIPTS`` carries every hook
template, including two that are opt-in per project -- the destructive-command
guard and memory auto-capture -- which only ``tapps init`` / ``tapps upgrade``
wire, and then only when a ``.tapps-mcp.yaml`` flag is set. The bundle has no
equivalent flag, so it copied both wholesale and emitted no ``hooks.json``
entry for either. The plugin's bash guard was therefore inert on install:
present, plausible, and never invoked. Nothing dangled, so nothing complained.

**A wired script that cannot run.** Commands were emitted relative to the
bundle root (``hooks/tapps-session-start.sh``), which Claude Code hands to the
shell as-is -- so they resolved against whatever directory the session started
in. Installing this bundle from its own marketplace on 2026-09-17 showed every
hook failing::

    Hook SessionStart:startup error:
      /bin/sh: 1: hooks/tapps-session-start.sh: not found
    SessionEnd:other [hooks/tapps-session-end.sh] completed with status 127

and, after anchoring them, the same probe on the same session shape::

    SessionStart:startup (SessionStart) success: ...
    SessionEnd:other ["${CLAUDE_PLUGIN_ROOT}/hooks/tapps-session-end.sh"]
      completed with status 0

``${CLAUDE_PLUGIN_ROOT}`` is the documented placeholder for a plugin's install
directory. Shell-form commands that use a placeholder are double-quoted, so an
install path containing spaces still resolves.

The two functions here are what keeps the bundle honest: the set of scripts it
ships is *derived* from the set its manifest references, so a hook that is not
wired is not shipped looking active.

``scripts/validate-claude-plugin.sh`` enforces the same two properties on the
built artifact, and
``scripts/test-validate-claude-plugin-hook-wiring.sh`` proves those checks
discriminate.
"""

from __future__ import annotations

import json
import shlex
import stat
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

__all__ = [
    "EXCLUDED_HOOKS_README_SECTION",
    "PLUGIN_HOOK_DIR",
    "plugin_hook_command",
    "referenced_script_names",
    "write_plugin_hooks",
]

# TAP-7754's acceptance allows an excluded hook either to be absent outright or
# to be "named explicitly in the bundle README with the reason". This is that
# note. It lives beside the code that does the excluding, so the two cannot
# come to describe different sets.
EXCLUDED_HOOKS_README_SECTION = """### Hooks not in this bundle

Two hooks `tapps-mcp init` / `upgrade` can install are deliberately **absent**
here, not merely unconfigured:

- `tapps-pre-bash.sh` — the destructive-command guard (`rm -rf`, `format c:`,
  fork bombs)
- `tapps-memory-auto-capture.sh` — writes durable facts from the transcript
  to the memory brain at session stop

Both are opt-in per project, gated behind a `.tapps-mcp.yaml` flag a plugin
bundle has no equivalent of. Earlier versions shipped them with no `hooks.json`
entry: present, plausible, never invoked. A safety guard that looks active and
is not is worse than an absent one, so the bundle ships only the hooks it
wires. To get either, install with `tapps-mcp init` and set the flag."""

_PROJECT_HOOK_DIR = ".claude/hooks/"
PLUGIN_HOOK_DIR = "${CLAUDE_PLUGIN_ROOT}/hooks/"


def plugin_hook_command(command: str) -> str:
    """Re-anchor a per-project hook command at the plugin's install directory.

    ``.claude/hooks/x.sh`` only exists for a ``tapps init`` install; inside a
    plugin the same script lives under ``${CLAUDE_PLUGIN_ROOT}/hooks/``.
    """
    return f'"{command.replace(_PROJECT_HOOK_DIR, PLUGIN_HOOK_DIR)}"'


def referenced_script_names(
    hooks_config: Mapping[str, Sequence[Mapping[str, Any]]],
) -> set[str]:
    """Return the basenames of every script the hook config actually wires.

    The bundle ships exactly this set. Deriving it here, rather than restating
    it as a list of exclusions, is what stops the manifest and the shipped
    files drifting apart again -- a new opt-in hook template is excluded
    automatically, with nobody needing to remember.
    """
    names: set[str] = set()
    for entries in hooks_config.values():
        for entry in entries:
            for hook in entry["hooks"]:
                tokens = shlex.split(hook["command"])
                if tokens:
                    names.add(PurePosixPath(tokens[0]).name)
    return names


# TAP-955: `if:` is honoured on tool events only; other events silently ignore
# it, so it is copied forward only where it means something.
_TOOL_EVENTS = frozenset(
    {
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionRequest",
        "PermissionDenied",
    }
)


def write_plugin_hooks(
    hooks_dir: Path,
    hooks_config: Mapping[str, Sequence[Mapping[str, Any]]],
    hook_scripts: Mapping[str, str],
    rewrite: Callable[[str], str],
) -> list[str]:
    """Write ``hooks.json`` and the scripts it wires. Returns bundle-relative paths.

    ``rewrite`` re-namespaces ``mcp__*`` tool references for the plugin; it is
    injected rather than imported to keep this module free of a cycle back into
    the bundler.

    The two invariants this function exists to hold, both of which shipped
    broken before TAP-7754: every command is anchored at the plugin root, and
    the scripts written are exactly the scripts the manifest references.
    """
    hooks_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    manifest: dict[str, Any] = {}
    for event, entries in hooks_config.items():
        plugin_entries = []
        for entry in entries:
            emitted: dict[str, Any] = {}
            if "matcher" in entry:
                emitted["matcher"] = rewrite(entry["matcher"])
            if event in _TOOL_EVENTS and "if" in entry:
                emitted["if"] = rewrite(entry["if"])
            emitted["hooks"] = [
                {"type": h["type"], "command": plugin_hook_command(h["command"])}
                for h in entry["hooks"]
            ]
            plugin_entries.append(emitted)
        manifest[event] = plugin_entries

    (hooks_dir / "hooks.json").write_text(
        json.dumps({"hooks": manifest}, indent=2) + "\n", encoding="utf-8"
    )
    written.append("hooks/hooks.json")

    referenced = referenced_script_names(hooks_config)
    for name, content in hook_scripts.items():
        if name not in referenced:
            # An opt-in hook the bundle cannot toggle. Shipping it unwired is
            # how the bash guard came to be inert on install.
            continue
        script_path = hooks_dir / name
        script_path.write_text(rewrite(content), encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        written.append(f"hooks/{name}")

    return written
