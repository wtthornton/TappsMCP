"""Plugin package builder for Claude Code marketplace distribution.

Generates a complete Claude Code plugin directory from TappsMCP's existing
templates: skills, agents, hooks, MCP config, and platform rules.

Usage::

    tapps-mcp build-plugin --output-dir ./tapps-mcp-plugin/
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.common.logging import get_logger
from tapps_mcp import __version__

log = get_logger(__name__)


@dataclass
class PluginBuilder:
    """Build a Claude Code plugin directory from TappsMCP templates."""

    output_dir: Path
    engagement_level: str = "medium"
    _result: dict[str, Any] = field(default_factory=dict)

    def build(self) -> Path:
        """Generate the complete plugin directory. Returns the output path."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._result = {"components": {}}

        self._generate_manifest()
        self._generate_skills()
        self._generate_agents()
        self._generate_hooks()
        self._generate_mcp_config()
        self._generate_rules()
        self._generate_settings()
        self._generate_bin()

        self._result["output_dir"] = str(self.output_dir)
        self._result["version"] = __version__
        log.info("plugin_built", output_dir=str(self.output_dir))
        return self.output_dir

    @property
    def result(self) -> dict[str, Any]:
        """Build result metadata."""
        return self._result

    # ------------------------------------------------------------------
    # Manifest
    # ------------------------------------------------------------------

    def _generate_manifest(self) -> None:
        manifest_dir = self.output_dir / ".claude-plugin"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "name": "tapps-mcp",
            "description": (
                "Deterministic code quality tools for Python — "
                "scoring, security, gates, expert consultation, and more."
            ),
            "version": __version__,
            "author": {"name": "TappsMCP"},
            "license": "MIT",
        }
        (manifest_dir / "plugin.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        self._result["components"]["manifest"] = "created"

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def _generate_skills(self) -> None:
        from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS

        skills_dir = self.output_dir / "skills"
        created: list[str] = []
        for name, content in CLAUDE_SKILLS.items():
            namespaced = f"tapps-mcp-{name}"
            skill_dir = skills_dir / namespaced
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
            created.append(namespaced)
        self._result["components"]["skills"] = created

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    def _generate_agents(self) -> None:
        from tapps_mcp.pipeline.platform_subagents import CLAUDE_AGENTS

        agents_dir = self.output_dir / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        created: list[str] = []
        for name, content in CLAUDE_AGENTS.items():
            (agents_dir / name).write_text(content, encoding="utf-8")
            created.append(name)
        self._result["components"]["agents"] = created

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    def _generate_hooks(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOKS_CONFIG

        hooks_dir = self.output_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        hooks_json: dict[str, list[dict[str, Any]]] = {}
        for event, entries in CLAUDE_HOOKS_CONFIG.items():
            hooks_json[event] = list(entries)

        (hooks_dir / "hooks.json").write_text(json.dumps(hooks_json, indent=2), encoding="utf-8")
        self._result["components"]["hooks"] = list(hooks_json.keys())

    # ------------------------------------------------------------------
    # MCP config
    # ------------------------------------------------------------------

    def _generate_mcp_config(self) -> None:
        mcp_config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "args": ["serve"],
                    "env": {"TAPPS_MCP_PROJECT_ROOT": "."},
                }
            }
        }
        (self.output_dir / ".mcp.json").write_text(
            json.dumps(mcp_config, indent=2), encoding="utf-8"
        )
        self._result["components"]["mcp_config"] = "created"

    # ------------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------------

    def _generate_rules(self) -> None:
        rules_dir = self.output_dir / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)

        rule_content = (
            "# Python Quality Rules (TappsMCP)\n\n"
            "## Enforcement\n"
            f"- Engagement level: {self.engagement_level}\n"
            "- Quality gate: must pass before declaring work complete\n"
            "- Security floor: minimum 50/100 on security category\n\n"
            "## Workflow\n"
            "1. Call `tapps_session_start` at the beginning of each session\n"
            "2. Use `tapps_quick_check` after editing Python files\n"
            "3. Run `tapps_validate_changed` before declaring work complete\n"
        )
        (rules_dir / "python-quality.md").write_text(rule_content, encoding="utf-8")
        self._result["components"]["rules"] = "created"

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _generate_settings(self) -> None:
        settings = {
            "permissions": {
                "allow": [
                    "mcp__tapps-mcp__*",
                ]
            }
        }
        (self.output_dir / "settings.json").write_text(
            json.dumps(settings, indent=2), encoding="utf-8"
        )
        self._result["components"]["settings"] = "created"

    # ------------------------------------------------------------------
    # bin/ shims (TAP-959)
    # ------------------------------------------------------------------

    def _generate_bin(self) -> None:
        import stat

        from tapps_mcp.pipeline.platform_bundles import (
            _BIN_SHIMS,
            _posix_shim,
            _windows_shim,
        )

        bin_dir = self.output_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        created: list[str] = []
        for shim_name, subcommand in _BIN_SHIMS.items():
            posix_path = bin_dir / shim_name
            posix_path.write_text(_posix_shim(subcommand), encoding="utf-8")
            posix_path.chmod(
                posix_path.stat().st_mode
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH
            )
            created.append(shim_name)

            cmd_path = bin_dir / f"{shim_name}.cmd"
            cmd_path.write_text(_windows_shim(subcommand), encoding="utf-8")
            created.append(f"{shim_name}.cmd")
        self._result["components"]["bin"] = {"count": len(created), "files": created}
