"""TAP-7754: a hook that ships must be wired, and a wired hook must run.

Two defects shipped on opposite sides of "the script exists", and the bundle's
referential-integrity check saw neither:

1. ``tapps-pre-bash.sh`` -- the destructive-command guard -- was copied into
   the bundle with no ``hooks.json`` entry, so the plugin's bash guard did
   nothing on install. It is opt-in per project, gated behind a
   ``.tapps-mcp.yaml`` flag the bundle has no equivalent of.
2. Commands were emitted relative (``hooks/tapps-session-start.sh``), so on a
   real install every hook failed ``not found`` / status 127.

These assert on the bundler, which produces the artifact.
``scripts/test-validate-claude-plugin-hook-wiring.sh`` covers the artifact and
the validator that inspects it.
"""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.pipeline.platform_generators import generate_claude_plugin_bundle

OPT_IN_HOOKS = ("tapps-pre-bash.sh", "tapps-memory-auto-capture.sh")


def _commands(bundle: Path) -> list[str]:
    data = json.loads((bundle / "hooks" / "hooks.json").read_text())["hooks"]
    found: list[str] = []
    for entries in data.values():
        for entry in entries:
            found.extend(h["command"] for h in entry["hooks"])
    return found


class TestHookWiring:
    def test_every_shipped_hook_script_is_referenced(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        commands = " ".join(_commands(tmp_path))
        shipped = {p.name for p in (tmp_path / "hooks").iterdir() if p.name != "hooks.json"}

        inert = sorted(name for name in shipped if name not in commands)
        assert not inert, f"bundle ships hook scripts no event references: {inert}"

    def test_opt_in_hooks_are_not_shipped(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        for name in OPT_IN_HOOKS:
            assert not (tmp_path / "hooks" / name).exists(), (
                f"{name} is opt-in per project and the bundle has no toggle for it; "
                f"shipping it unwired is the TAP-7754 defect"
            )

    def test_opt_in_hooks_remain_available_to_the_per_project_installer(self):
        """The exclusion is the bundle's, not a deletion of the hooks.

        Guards against "fixing" this by removing the guard outright, which
        would satisfy the test above and lose a real safety control.
        """
        from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOK_SCRIPTS

        for name in OPT_IN_HOOKS:
            assert name in CLAUDE_HOOK_SCRIPTS

    def test_every_command_is_anchored_at_the_plugin_root(self, tmp_path):
        generate_claude_plugin_bundle(tmp_path)
        commands = _commands(tmp_path)

        assert commands, "no hook commands emitted at all"
        unanchored = [c for c in commands if "${CLAUDE_PLUGIN_ROOT}/hooks/" not in c]
        assert not unanchored, (
            f"{len(unanchored)} hook command(s) not anchored at the plugin root; "
            f"these resolve against the session's cwd and fail at runtime: {unanchored}"
        )

    def test_commands_are_quoted_for_paths_containing_spaces(self, tmp_path):
        """Shell-form commands using a placeholder must be double-quoted."""
        generate_claude_plugin_bundle(tmp_path)
        for command in _commands(tmp_path):
            assert command.startswith('"') and command.endswith('"'), (
                f"unquoted hook command would split on a plugin path containing spaces: {command}"
            )
