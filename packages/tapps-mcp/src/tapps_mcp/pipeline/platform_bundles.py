"""Plugin bundle generators, agent teams hooks, and CI workflow.

Contains plugin bundle generation (Claude + Cursor), agent teams hooks,
and CI workflow generation. Rules, Copilot instructions, and BugBot
rules are in ``platform_rules.py``.
Extracted from ``platform_generators.py`` to reduce file size.
"""

from __future__ import annotations

import base64
import json
import stat
from typing import TYPE_CHECKING, Any

from tapps_mcp.pipeline.platform_hook_templates import (
    AGENT_TEAMS_CLAUDE_MD_SECTION,
    AGENT_TEAMS_HOOK_SCRIPTS,
    AGENT_TEAMS_HOOKS_CONFIG,
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOKS_CONFIG,
    CURSOR_HOOK_SCRIPTS,
    CURSOR_HOOKS_CONFIG,
    INVALID_CLAUDE_HOOK_KEYS,
    SUPPORTED_CLAUDE_HOOK_KEYS,  # noqa: F401  (re-export for external callers)
)
from tapps_mcp.pipeline.platform_rules import (
    CURSOR_RULE_TEMPLATES,
)
from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS, CURSOR_SKILLS
from tapps_mcp.pipeline.platform_subagents import CLAUDE_AGENTS, CURSOR_AGENTS

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# bin/ shim scripts (TAP-959)
# ---------------------------------------------------------------------------
#
# Claude Code auto-adds an enabled plugin's bin/ directory to the Bash tool's
# PATH, so shipping shims lets callers type `tapps-quick-lint foo.py` instead
# of `uvx tapps-mcp validate-changed foo.py`. Each shim prefers a directly-
# installed `tapps-mcp` (pip/uv/pipx) and falls back to `uvx tapps-mcp`.

_BIN_SHIMS: dict[str, list[str]] = {
    "tapps-quick-lint": ["validate-changed", "--quick"],
    "tapps-doctor-cli": ["doctor"],
}


def _posix_shim(subcommand: list[str]) -> str:
    """Emit a POSIX bash shim that prefers a direct `tapps-mcp` entrypoint."""
    args = " ".join(subcommand)
    return (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        f'if command -v tapps-mcp >/dev/null 2>&1; then\n'
        f'  exec tapps-mcp {args} "$@"\n'
        f'fi\n'
        f'exec uvx tapps-mcp {args} "$@"\n'
    )


def _windows_shim(subcommand: list[str]) -> str:
    """Emit a Windows .cmd shim matching the POSIX behavior."""
    args = " ".join(subcommand)
    return (
        "@echo off\r\n"
        "where tapps-mcp >nul 2>nul\r\n"
        "if %ERRORLEVEL%==0 (\r\n"
        f"  tapps-mcp {args} %*\r\n"
        ") else (\r\n"
        f"  uvx tapps-mcp {args} %*\r\n"
        ")\r\n"
    )


# ---------------------------------------------------------------------------
# monitors/ — background health streams (TAP-960)
# ---------------------------------------------------------------------------
#
# Claude Code 2.1+ reads monitors/monitors.json and streams each monitor's
# stdout lines as session notifications. Off by default — callers opt in via
# `.tapps-mcp.yaml` (`monitors.enabled: true`). Three baseline monitors:
#
#   tapps-brain-health — poll tapps-brain /health every 30s for drift.
#   quality-gate-watch — tail tapps-mcp validate-changed output aggregator.
#   ralph-live-tail    — tail .ralph/live.log when ralph is running.

_MONITORS_CONFIG: dict[str, Any] = {
    "monitors": [
        {
            "name": "tapps-brain-health",
            "when": "always",
            "command": (
                "${CLAUDE_PLUGIN_ROOT}/bin/tapps-doctor-cli --brain-only --watch"
            ),
            "description": (
                "Polls tapps-brain /health every 30s and surfaces status drift."
            ),
        },
        {
            "name": "quality-gate-watch",
            "when": "always",
            "command": (
                "${CLAUDE_PLUGIN_ROOT}/bin/tapps-quick-lint --watch --summary"
            ),
            "description": (
                "Aggregates recent tapps_quality_gate failures and emits one-line "
                "notifications when a new failure appears."
            ),
        },
        {
            "name": "ralph-live-tail",
            "when": "always",
            "command": 'tail -F .ralph/live.log 2>/dev/null || true',
            "description": (
                "Tails .ralph/live.log when the Ralph loop is running. Harmless "
                "no-op when the file is absent."
            ),
        },
    ],
}


# ---------------------------------------------------------------------------
# Agent Teams hooks (Story 12.12)
# ---------------------------------------------------------------------------


def generate_agent_teams_hooks(
    project_root: Path,
) -> dict[str, Any]:
    """Generate Agent Teams hook scripts and merge config.

    Creates ``tapps-teammate-idle.sh`` and
    ``tapps-teams-task-completed.sh`` in ``.claude/hooks/`` and merges
    ``TeammateIdle`` and ``TaskCompleted`` entries into
    ``.claude/settings.json``.

    Returns a summary dict.
    """
    hooks_dir = project_root / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    scripts_created: list[str] = []
    for name, content in AGENT_TEAMS_HOOK_SCRIPTS.items():
        script_path = hooks_dir / name
        if not script_path.exists():
            script_path.write_text(content, encoding="utf-8")
            script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
            scripts_created.append(name)

    # Merge hooks config into .claude/settings.json
    settings_file = project_root / ".claude" / "settings.json"
    if settings_file.exists():
        raw = settings_file.read_text(encoding="utf-8")
        config: dict[str, Any] = json.loads(raw) if raw.strip() else {}
    else:
        config = {}

    existing_hooks: dict[str, Any] = config.setdefault("hooks", {})
    hooks_added = 0
    for event, entries in AGENT_TEAMS_HOOKS_CONFIG.items():
        if event not in existing_hooks:
            existing_hooks[event] = entries
            hooks_added += len(entries)

    config["hooks"] = {
        k: v for k, v in config["hooks"].items() if k not in INVALID_CLAUDE_HOOK_KEYS
    }
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    return {
        "scripts_created": scripts_created,
        "hooks_added": hooks_added,
    }


def get_agent_teams_claude_md_section() -> str:
    """Return the Agent Teams documentation section."""
    return AGENT_TEAMS_CLAUDE_MD_SECTION


# ---------------------------------------------------------------------------
# Plugin bundle generators (Stories 12.9 + 12.10)
# ---------------------------------------------------------------------------

_CLAUDE_PLUGIN_README = """\
# TappsMCP - Claude Code Plugin

Code quality scoring, security scanning, and quality gates
for Python projects.

## Installation

Place this directory as a Claude Code plugin or install via:

```
claude plugin install tapps-mcp
```

## What's Included

- **MCP Server**: `tapps-mcp serve` with 12+ quality tools
- **Agents**: tapps-reviewer, tapps-researcher, tapps-validator
- **Skills**: `/tapps-score`, `/tapps-gate`, `/tapps-validate`
- **Hooks**: Session start, post-edit reminders, stop gate

## Usage

Once installed, the TappsMCP tools are available in every
session. Use `/tapps-score` to score a file, `/tapps-gate` to
run quality gates, and `/tapps-validate` before declaring
work complete.
"""

_CURSOR_PLUGIN_README = """\
# TappsMCP - Cursor Plugin

Code quality scoring, security scanning, and quality gates
for Python projects.

## Installation

Install via Cursor marketplace or place this directory as a
Cursor plugin.

## What's Included

- **MCP Server**: `tapps-mcp serve` with 12+ quality tools
- **Agents**: tapps-reviewer, tapps-researcher, tapps-validator
- **Skills**: `@tapps-score`, `@tapps-gate`, `@tapps-validate`
- **Hooks**: Before MCP, after edit reminders, stop prompt
- **Rules**: Pipeline (always), Python quality (auto-attach),
  Expert consultation (agent-requested)

## Usage

Once installed, the TappsMCP tools are available in every
session. Use `@tapps-score` to score a file, `@tapps-gate` to
run quality gates, and `@tapps-validate` before declaring
work complete.
"""


def generate_claude_plugin_bundle(
    output_dir: Path,
    version: str = "0.3.0",
    *,
    monitors_enabled: bool = False,
) -> dict[str, Any]:
    """Generate a Claude Code plugin bundle directory.

    Creates the full plugin directory structure under *output_dir*
    including plugin.json, agents, skills, hooks, .mcp.json,
    and README.md.

    When ``monitors_enabled`` is True (TAP-960), an opt-in
    ``monitors/monitors.json`` is emitted to stream TappsMCP-relevant logs
    (tapps-brain health, quality-gate failures, .ralph/live.log tail) into
    the session as Claude Code notifications. Off by default; callers driving
    this from ``.tapps-mcp.yaml`` (``monitors.enabled: true``) should pass
    the resolved value.

    Returns a summary dict with ``files_created``.
    """
    files_created: list[str] = []

    # .claude-plugin/plugin.json — TAP-958: extended with userConfig, author,
    # repository, license, homepage, and dependencies so Claude Code 2.1+ can
    # prompt the user at enable time and resolve cross-plugin dependencies.
    meta_dir = output_dir / ".claude-plugin"
    meta_dir.mkdir(parents=True, exist_ok=True)
    plugin_data: dict[str, Any] = {
        "name": "tapps-mcp",
        "version": version,
        "description": (
            "Code quality scoring, security scanning, and quality gates for Python projects"
        ),
        "author": "TappsMCP Contributors",
        "license": "MIT",
        "homepage": "https://github.com/tapps-mcp/tapps-mcp",
        "repository": "https://github.com/tapps-mcp/tapps-mcp",
        "userConfig": {
            "engagement_level": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "default": "high",
                "description": (
                    "How assertively TappsMCP prompts quality checks. "
                    "'high' runs validators on every edit; 'low' runs only on explicit request."
                ),
            },
            "memory_http_url": {
                "type": "string",
                "default": "http://localhost:8080",
                "description": (
                    "tapps-brain HTTP endpoint for cross-session memory. "
                    "Leave at default if running tapps-brain locally via Docker."
                ),
            },
            "quality_preset": {
                "type": "string",
                "enum": ["standard", "strict", "framework"],
                "default": "standard",
                "description": "Quality gate preset applied by tapps_quality_gate.",
            },
        },
        "dependencies": {
            # Semver-compatible range. docs-mcp tracks tapps-mcp version; keep
            # the floor at the matching release and allow same-major bumps.
            "docs-mcp": f"^{version}",
        },
    }
    (meta_dir / "plugin.json").write_text(
        json.dumps(plugin_data, indent=2) + "\n", encoding="utf-8"
    )
    files_created.append(".claude-plugin/plugin.json")

    # agents/
    agents_dir = output_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name, content in CLAUDE_AGENTS.items():
        (agents_dir / name).write_text(content, encoding="utf-8")
        files_created.append(f"agents/{name}")

    # skills/
    for skill_name, content in CLAUDE_SKILLS.items():
        skill_dir = output_dir / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        files_created.append(f"skills/{skill_name}/SKILL.md")

    # hooks/
    hooks_dir = output_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hooks_json_data: dict[str, Any] = {}
    # TAP-955: propagate `if:` matchers on tool-event entries so Claude Code
    # can skip the hook when the tool call doesn't match. Non-tool events
    # (SessionStart, Stop, SessionEnd, etc.) silently ignore `if:`, but we
    # only copy it forward to keep the emitted manifest clean.
    _TOOL_EVENTS = frozenset(
        {
            "PreToolUse",
            "PostToolUse",
            "PostToolUseFailure",
            "PermissionRequest",
            "PermissionDenied",
        }
    )
    for event, entries in CLAUDE_HOOKS_CONFIG.items():
        plugin_entries = []
        for entry in entries:
            pe: dict[str, Any] = {}
            if "matcher" in entry:
                pe["matcher"] = entry["matcher"]
            if event in _TOOL_EVENTS and "if" in entry:
                pe["if"] = entry["if"]
            pe["hooks"] = [
                {
                    "type": h["type"],
                    "command": h["command"].replace(".claude/hooks/", "hooks/"),
                }
                for h in entry["hooks"]
            ]
            plugin_entries.append(pe)
        hooks_json_data[event] = plugin_entries
    (hooks_dir / "hooks.json").write_text(
        json.dumps({"hooks": hooks_json_data}, indent=2) + "\n",
        encoding="utf-8",
    )
    files_created.append("hooks/hooks.json")

    for name, content in CLAUDE_HOOK_SCRIPTS.items():
        script_path = hooks_dir / name
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        files_created.append(f"hooks/{name}")

    # bin/ — TAP-959: shim scripts auto-PATHed by Claude Code when the plugin
    # is enabled. Each shim prefers a pip/uv-installed `tapps-mcp` if present,
    # else falls back to `uvx tapps-mcp`. POSIX .sh stays at `/usr/bin/env bash`;
    # .cmd variants ship alongside for Windows.
    bin_dir = output_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for shim_name, subcommand in _BIN_SHIMS.items():
        posix_path = bin_dir / shim_name
        posix_path.write_text(_posix_shim(subcommand), encoding="utf-8")
        posix_path.chmod(
            posix_path.stat().st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH
        )
        files_created.append(f"bin/{shim_name}")

        cmd_path = bin_dir / f"{shim_name}.cmd"
        cmd_path.write_text(_windows_shim(subcommand), encoding="utf-8")
        files_created.append(f"bin/{shim_name}.cmd")

    # monitors/ — TAP-960: opt-in background health streams. Only emitted
    # when the caller passes monitors_enabled=True (driven by .tapps-mcp.yaml).
    if monitors_enabled:
        monitors_dir = output_dir / "monitors"
        monitors_dir.mkdir(parents=True, exist_ok=True)
        (monitors_dir / "monitors.json").write_text(
            json.dumps(_MONITORS_CONFIG, indent=2) + "\n", encoding="utf-8"
        )
        files_created.append("monitors/monitors.json")

    # .mcp.json — ${user_config.*} substitutions are resolved by Claude Code
    # at enable time from the plugin.json userConfig values (TAP-958).
    mcp_config = {
        "mcpServers": {
            "tapps-mcp": {
                "command": "uvx",
                "args": ["tapps-mcp", "serve"],
                "env": {
                    "TAPPS_MCP_PROJECT_ROOT": ".",
                    "TAPPS_BRAIN_HTTP_URL": "${user_config.memory_http_url}",
                    "TAPPS_LLM_ENGAGEMENT_LEVEL": "${user_config.engagement_level}",
                    "TAPPS_QUALITY_PRESET": "${user_config.quality_preset}",
                },
            },
        },
    }
    (output_dir / ".mcp.json").write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")
    files_created.append(".mcp.json")

    # README.md
    (output_dir / "README.md").write_text(_CLAUDE_PLUGIN_README, encoding="utf-8")
    files_created.append("README.md")

    return {"files_created": files_created}


def generate_cursor_plugin_bundle(
    output_dir: Path,
    version: str = "0.3.0",
) -> dict[str, Any]:
    """Generate a Cursor plugin bundle directory.

    Creates the full plugin directory structure under *output_dir*
    including plugin.json, agents, skills, hooks, rules, mcp.json,
    logo.png placeholder, and README.md.

    Returns a summary dict with ``files_created``.
    """
    files_created: list[str] = []

    # .cursor-plugin/plugin.json
    meta_dir = output_dir / ".cursor-plugin"
    meta_dir.mkdir(parents=True, exist_ok=True)
    plugin_data = {
        "name": "tapps-mcp-plugin",
        "displayName": "TappsMCP Quality Tools",
        "author": "TappsMCP Team",
        "description": (
            "Code quality scoring, security scanning, and quality gates for Python projects"
        ),
        "keywords": [
            "code-quality",
            "security",
            "scoring",
            "mcp",
            "python",
        ],
        "license": "MIT",
        "version": version,
    }
    (meta_dir / "plugin.json").write_text(
        json.dumps(plugin_data, indent=2) + "\n", encoding="utf-8"
    )
    files_created.append(".cursor-plugin/plugin.json")

    # agents/
    agents_dir = output_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name, content in CURSOR_AGENTS.items():
        (agents_dir / name).write_text(content, encoding="utf-8")
        files_created.append(f"agents/{name}")

    # skills/
    for skill_name, content in CURSOR_SKILLS.items():
        skill_dir = output_dir / "skills" / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
        files_created.append(f"skills/{skill_name}/SKILL.md")

    # hooks/
    hooks_dir = output_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    cursor_hooks_obj: dict[str, list[dict[str, str]]] = {
        event: [{"command": cmd["command"].replace(".cursor/hooks/", "hooks/")} for cmd in cmds]
        for event, cmds in CURSOR_HOOKS_CONFIG.items()
    }
    (hooks_dir / "hooks.json").write_text(
        json.dumps({"version": 1, "hooks": cursor_hooks_obj}, indent=2) + "\n",
        encoding="utf-8",
    )
    files_created.append("hooks/hooks.json")

    for name, content in CURSOR_HOOK_SCRIPTS.items():
        script_path = hooks_dir / name
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        files_created.append(f"hooks/{name}")

    # rules/
    rules_dir = output_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    for name, content in CURSOR_RULE_TEMPLATES.items():
        (rules_dir / name).write_text(content, encoding="utf-8")
        files_created.append(f"rules/{name}")

    # mcp.json
    mcp_config = {
        "mcpServers": {
            "tapps-mcp": {
                "command": "uvx",
                "args": ["tapps-mcp", "serve"],
                "env": {
                    "TAPPS_MCP_PROJECT_ROOT": ("${workspaceFolder}"),
                },
            },
        },
    }
    (output_dir / "mcp.json").write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")
    files_created.append("mcp.json")

    # logo.png placeholder (1x1 transparent PNG)
    _png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5E"
        "rkJggg=="
    )
    (output_dir / "logo.png").write_bytes(base64.b64decode(_png))
    files_created.append("logo.png")

    # README.md
    (output_dir / "README.md").write_text(_CURSOR_PLUGIN_README, encoding="utf-8")
    files_created.append("README.md")

    # LICENSE
    license_text = "MIT License\n\nCopyright (c) TappsMCP Team\n"
    (output_dir / "LICENSE").write_text(license_text, encoding="utf-8")
    files_created.append("LICENSE")

    return {"files_created": files_created}


# ---------------------------------------------------------------------------
# CI / Headless workflow — removed
# ---------------------------------------------------------------------------
# The `generate_ci_workflow` generator used to emit `tapps-quality.yml` into
# consumer projects. That workflow was removed so quality work runs locally
# via the TappsMCP pipeline rather than in GitHub Actions. CodeQL remains
# (see `github_ci.generate_codeql_workflow`). Do not reintroduce the quality
# workflow here — if a consumer wants it, they can call the quality gate
# from their own CI without TappsMCP installing it for them.


_CI_CLAUDE_MD_SECTION = """\

## CI Integration

TappsMCP can run in CI without an interactive session:

### Direct Python invocation (recommended for CI)

```bash
# Install TappsMCP
pip install tapps-mcp

# Validate changed files
TAPPS_MCP_PROJECT_ROOT=/workspace \\
  tapps-mcp validate-changed --preset staging
```

### Claude Code headless mode

```bash
claude --headless \\
  --allowedTools "mcp__tapps-mcp__tapps_validate_changed" \\
  "Run tapps_validate_changed with preset=staging"
```

### VS Code / headless - enableAllProjectMcpServers

In headless or non-interactive VS Code contexts, set:
`claude.enableAllProjectMcpServers: true` in workspace settings.

### Setup hook for CI onboarding

```bash
claude --init-only \\
  --allowedTools "mcp__tapps-mcp__*" \\
  --project-root /workspace
```
"""


def get_ci_claude_md_section() -> str:
    """Return the CI Integration documentation section for CLAUDE.md.

    Kept as a docs stub — the text explains how consumers can *invoke*
    tapps-mcp from their own CI if they want. TappsMCP no longer generates
    CI workflow files on their behalf.
    """
    return _CI_CLAUDE_MD_SECTION


# ---------------------------------------------------------------------------
# Path-scoped Python quality rules for Claude Code (Epic 33.3)
# ---------------------------------------------------------------------------

_PYTHON_QUALITY_RULE_HIGH = """\
---
paths:
  - "**/*.py"
---
# Python Quality Rules (TappsMCP)

REQUIRED: Run `tapps_quick_check(file_path)` after editing Python files.

REQUIRED: Call `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths before declaring work complete. Never call without `file_paths`. Default is quick mode; only use `quick=false` as a last resort.

REQUIRED: Use `tapps_lookup_docs(library, topic)` before using unfamiliar library APIs.

Do NOT mark tasks complete if quality gate has not passed.

## Quality Scoring (7 Categories, 0-100 each)

1. **Complexity** - Cyclomatic complexity (radon cc / AST fallback)
2. **Security** - Bandit + pattern heuristics
3. **Maintainability** - Maintainability index (radon mi / AST fallback)
4. **Test Coverage** - Heuristic from matching test file existence
5. **Performance** - Halstead metrics, perflint anti-patterns, nested loops, large functions, deep nesting
6. **Structure** - Project layout (pyproject.toml, tests/, README, .git)
7. **DevEx** - Developer experience (docs, AGENTS.md, tooling config)

Any category scoring below 70 MUST be addressed immediately.
"""

_PYTHON_QUALITY_RULE_MEDIUM = """\
---
paths:
  - "**/*.py"
---
# Python Quality Rules (TappsMCP)

Run `tapps_quick_check(file_path)` after editing Python files.

Use `tapps_lookup_docs(library, topic)` before using unfamiliar library APIs.

Call `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths before declaring work complete. Never call without `file_paths`. Default is quick mode; only use `quick=false` as a last resort.

## Quality Scoring (7 Categories, 0-100 each)

1. **Complexity** - Cyclomatic complexity (radon cc / AST fallback)
2. **Security** - Bandit + pattern heuristics
3. **Maintainability** - Maintainability index (radon mi / AST fallback)
4. **Test Coverage** - Heuristic from matching test file existence
5. **Performance** - Halstead metrics, perflint anti-patterns, nested loops, large functions, deep nesting
6. **Structure** - Project layout (pyproject.toml, tests/, README, .git)
7. **DevEx** - Developer experience (docs, AGENTS.md, tooling config)

Any category scoring below 70 should be addressed.
"""

_PYTHON_QUALITY_RULE_LOW = """\
---
paths:
  - "**/*.py"
---
# Python Quality Rules (TappsMCP)

Consider running `tapps_quick_check(file_path)` after editing Python files.

Consider using `tapps_lookup_docs(library, topic)` for unfamiliar APIs.

Consider calling `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths before declaring work complete. Default is quick mode; only use `quick=false` as a last resort.

## Quality Scoring (7 Categories, 0-100 each)

1. **Complexity** - Cyclomatic complexity (radon cc / AST fallback)
2. **Security** - Bandit + pattern heuristics
3. **Maintainability** - Maintainability index (radon mi / AST fallback)
4. **Test Coverage** - Heuristic from matching test file existence
5. **Performance** - Halstead metrics, perflint anti-patterns, nested loops, large functions, deep nesting
6. **Structure** - Project layout (pyproject.toml, tests/, README, .git)
7. **DevEx** - Developer experience (docs, AGENTS.md, tooling config)

Categories scoring below 70 may benefit from attention.
"""

_PYTHON_QUALITY_RULES: dict[str, str] = {
    "high": _PYTHON_QUALITY_RULE_HIGH,
    "medium": _PYTHON_QUALITY_RULE_MEDIUM,
    "low": _PYTHON_QUALITY_RULE_LOW,
}


def generate_python_quality_rule(engagement_level: str = "medium") -> str:
    """Return the Python quality rule content for the given engagement level.

    The rule uses ``paths:`` YAML frontmatter to scope activation to Python
    files only (``**/*.py``).

    Args:
        engagement_level: ``"high"``, ``"medium"`` (default), or ``"low"``.

    Returns:
        The full rule file content including frontmatter.
    """
    return _PYTHON_QUALITY_RULES.get(engagement_level, _PYTHON_QUALITY_RULE_MEDIUM)


def generate_claude_python_quality_rule(
    project_root: Path,
    engagement_level: str = "medium",
) -> dict[str, Any]:
    """Generate ``.claude/rules/python-quality.md`` with path-scoped frontmatter.

    Creates the ``.claude/rules/`` directory if needed and writes (or
    overwrites) the rule file. The rule uses ``paths: ["**/*.py"]`` so it
    only activates when Claude reads Python files.

    Args:
        project_root: Target project root directory.
        engagement_level: ``"high"``, ``"medium"``, or ``"low"``.

    Returns:
        A summary dict with ``file`` and ``action``.
    """
    rules_dir = project_root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "python-quality.md"
    existed = target.exists()
    content = generate_python_quality_rule(engagement_level)
    target.write_text(content, encoding="utf-8")
    action = "updated" if existed else "created"
    return {"file": str(target), "action": action}


_CLAUDE_AGENT_SCOPE_RULE = """\
---
alwaysApply: true
---
# Deployed Agent Scope (TappsMCP)

Agents deployed by `tapps_init` / `tapps_upgrade` (and Claude Code itself
working in this project) must stay scoped to THIS repo and THIS project for
any **write** operation.

## Allowed (read)

- Documentation lookups across any project (`tapps_lookup_docs`, web search,
  reading sibling repos).
- Searching memory across federated projects to inform decisions.
- Cloning or browsing other repositories for reference only.

## Forbidden (write outside the deploying project)

- Creating, updating, commenting on, or moving Linear (or other tracker)
  issues that belong to a different project than this repo.
- Modifying files, branches, or pull requests in any other repository.
- Pushing, merging, releasing, or running automation on behalf of another
  project.

## How to apply

- When using the Linear MCP tools (`mcp__plugin_linear_linear__*` or any
  successor), only operate on issues whose `team` / `project` matches the
  one configured for this repo. Read team/project identity from
  `.tapps-mcp.yaml` or the current git remote — never from arbitrary search
  results that point at other workspaces.
- When in doubt about whether a target belongs to this project, **stop and
  ask the user** instead of writing.
- Updates to this agent itself flow through `tapps_upgrade` re-running in
  this project, never via cross-project agent edits.
"""


def generate_claude_agent_scope_rule(
    project_root: Path,
) -> dict[str, Any]:
    """Generate ``.claude/rules/agent-scope.md``.

    Always-apply rule that bounds deployed-agent write operations to the
    deploying repo + project. Reading external context stays allowed.
    Idempotent — re-running overwrites with the same content.

    Args:
        project_root: Target project root directory.

    Returns:
        A summary dict with ``file`` and ``action``.
    """
    rules_dir = project_root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "agent-scope.md"
    existed = target.exists()
    target.write_text(_CLAUDE_AGENT_SCOPE_RULE, encoding="utf-8")
    return {"file": str(target), "action": "updated" if existed else "created"}


def generate_claude_pipeline_rule(
    project_root: Path,
) -> dict[str, Any]:
    """Generate ``.claude/rules/tapps-pipeline.md`` with path-scoped frontmatter.

    This rule file contains the detailed 5-stage pipeline, consequences table,
    CI integration, and agent teams info that was previously in CLAUDE.md.
    It only activates when working on Python or infrastructure files.

    Args:
        project_root: Target project root directory.

    Returns:
        A summary dict with ``file`` and ``action``.
    """
    rules_dir = project_root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "tapps-pipeline.md"
    existed = target.exists()

    content = """\
---
paths:
  - "**/*.py"
  - "Dockerfile*"
  - "docker-compose*.yml"
  - "pyproject.toml"
  - ".tapps-mcp.yaml"
---
# TAPPS Pipeline Details

## 5-Stage Pipeline

Recommended order for every code task:

1. **Discover** - `tapps_session_start()`, consider `tapps_memory(action="search")` for project context
2. **Research** - `tapps_lookup_docs()` for libraries and domain decisions
3. **Develop** - `tapps_score_file(file_path, quick=True)` during edit-lint-fix loops
4. **Validate** - `tapps_quick_check()` per file OR `tapps_validate_changed()` for batch
5. **Verify** - `tapps_checklist(task_type)`, consider `tapps_memory(action="save")` for learnings

## Consequences of Skipping

| Skipped Tool | Consequence |
|---|---|
| `tapps_session_start` | No project context - tools give generic advice |
| `tapps_lookup_docs` | Hallucinated APIs - code may fail at runtime |
| `tapps_quick_check` / scoring | Quality issues may ship silently |
| `tapps_quality_gate` | No quality bar enforced |
| `tapps_security_scan` | Vulnerabilities may ship to production |
| `tapps_checklist` | No verification that process was followed |
| `tapps_impact_analysis` | Refactoring may break unknown dependents |
| `tapps_dead_code` | Unused code may accumulate |
| `tapps_dependency_scan` | Vulnerable dependencies may ship |
| `tapps_dependency_graph` | Circular imports may cause runtime crashes |

## Response Guidance

Every tool response includes:
- `next_steps`: Up to 3 imperative actions to take next - consider following them
- `pipeline_progress`: Which stages are complete and what comes next

Record progress in `docs/TAPPS_HANDOFF.md` and `docs/TAPPS_RUNLOG.md`.
For task-specific tool call order, use the `tapps_workflow` MCP prompt.

## Agent Teams (Optional)

If using Claude Code Agent Teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`),
consider designating one teammate as a **quality watchdog**. To enable Agent Teams hooks, re-run `tapps_init` with `agent_teams=True`.

## CI Integration

TappsMCP can run in CI. Use `TAPPS_MCP_PROJECT_ROOT` and `tapps-mcp validate-changed --preset staging`, or Claude Code headless mode with `tapps_validate_changed`.
"""

    target.write_text(content, encoding="utf-8")
    action = "updated" if existed else "created"
    return {"file": str(target), "action": action}


_CLAUDE_LINEAR_STANDARDS_RULE = """\
---
alwaysApply: true
---
# Linear Issue Standards (TappsMCP)

All Linear writes in this project — epic creation, story creation, issue updates — MUST route through the `linear-issue` skill, which in turn routes through the docs-mcp generator and validator tools. Raw calls to `mcp__plugin_linear_linear__save_issue` are a rule violation.

## Required flow

### For a new epic
1. `mcp__docs-mcp__docs_generate_epic(title, purpose_and_intent, goal, motivation, acceptance_criteria, stories, ...)` — produces `docs/epics/EPIC-<N>.md` in the template shape.
2. `mcp__docs-mcp__docs_validate_linear_issue(title, description, is_epic=true)` — must return `agent_ready: true` with score 100.
3. Confirm with user.
4. `mcp__plugin_linear_linear__save_issue(...)` to push.
5. Create each child story via the story flow with `parent_id=<epic TAP-id>`.
6. `mcp__tapps-mcp__tapps_linear_snapshot_invalidate(team, project)`.

### For a new story
1. `mcp__docs-mcp__docs_generate_story(title, files, acceptance_criteria, ...)` — emits the 5-section template (`## What` / `## Where` / `## Why` / `## Acceptance` / `## Refs`).
2. `mcp__docs-mcp__docs_validate_linear_issue(title, description)` — must return `agent_ready: true`.
3. Confirm with user.
4. `mcp__plugin_linear_linear__save_issue(..., parent_id=<epic>)`.
5. `mcp__tapps-mcp__tapps_linear_snapshot_invalidate(team, project)`.

### Before updating an existing issue
1. `mcp__plugin_linear_linear__get_issue(id)` — fetch current state.
2. `mcp__docs-mcp__docs_lint_linear_issue(title, description, labels, priority, estimate)` — surface findings.
3. Regenerate via `docs_generate_story` or manual edit only if the existing body is broken.
4. Validate before push.
5. `save_issue(id=..., description=...)`; invalidate cache.

## Formatting rules (enforced by docs-mcp validator)

- Title <= 80 characters; no em-dash preambles.
- `## Acceptance` must contain at least one `- [ ]` checkbox.
- `## Where` must contain at least one `file.ext:LINE-RANGE` anchor.
- Bare `TAP-###` references, never `<issue id="UUID">TAP-###</issue>` wrappers.

## Linear markdown workarounds (observed 2026-04-24)

Linear's server-side markdown processor silently drops some content. These patterns preserve data:

- **Numbered lists, not bulleted, in `## Where` and `## Acceptance`** when items reference file paths. Bulleted `* path/...` entries get deduped on auto-linked filenames (especially `.md` files), keeping only the first. Numbered lists (`1.`, `2.`) survive intact.
- **Inline-code file paths**: `` `path/to/file.py:1-100` `` rather than bare `path/to/file.py:1-100`. Prevents the auto-linker from mangling.
- **Don't write bare `.md` filenames in prose** when a markdown auto-link would interfere. Use "the agents-md template", "the claude-md file", or wrap in backticks.
- **Avoid tables with many columns** — Linear's table rendering is fragile; prefer numbered lists with `—` separators for row fields.

## How to apply

When the user says "create a Linear issue", "file an epic", "open a ticket for X", or "track this in Linear" — invoke the `linear-issue` skill. Do not call `save_issue` directly. If the skill is unavailable in the session, flag it to the user rather than falling back to raw writes.

When updating an existing issue, the same routing applies: fetch, lint/validate, regenerate or edit, re-validate, save, invalidate.

## Enforcement

Currently soft-enforced (rule is auto-loaded into the system prompt). A follow-up ticket covers adding a `PreToolUse` hook that blocks `mcp__plugin_linear_linear__save_issue` when no prior `docs_validate_linear_issue` call has been recorded in the same turn cluster.
"""


def generate_claude_linear_standards_rule(
    project_root: Path,
) -> dict[str, Any]:
    """Generate ``.claude/rules/linear-standards.md``.

    Always-apply rule that requires Linear epic/story/issue writes to route
    through the docs-mcp generator and validator tools (via the
    ``linear-issue`` skill) rather than raw plugin ``save_issue`` calls.
    Captures the Linear markdown-rendering workarounds discovered during
    the TAP-971 fleet audit so agents reproduce compliant issues.
    Idempotent — re-running overwrites with the same content.

    Args:
        project_root: Target project root directory.

    Returns:
        A summary dict with ``file`` and ``action``.
    """
    rules_dir = project_root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "linear-standards.md"
    existed = target.exists()
    target.write_text(_CLAUDE_LINEAR_STANDARDS_RULE, encoding="utf-8")
    return {"file": str(target), "action": "updated" if existed else "created"}


# ---------------------------------------------------------------------------
# Scoped rules: security.md / test-quality.md / config-files.md (TAP-978)
# ---------------------------------------------------------------------------
#
# These three rules existed in tapps-mcp's own .claude/rules/ from the
# 2026 control-files audit but were never wired through the
# init/upgrade pipeline, so consumer fleets (AgentForge, NLTlabsPE,
# ralph-claude-code) were missing them. TAP-978 ships them through
# dedicated generators with skip tokens and doctor checks, mirroring
# the pattern used for python_quality_rule / pipeline_rule.
#
# Gating model (chosen over pure-universal because rule bodies are
# language/infra-specific):
#
# - security_rule, test_quality_rule:
#     Python-gated (mirrors python_quality_rule). The bodies discuss
#     Bandit, path validators, pickle, pytest fixtures — Python-only
#     concerns that would be misleading on JS/Go/Rust repos.
# - config_files_rule:
#     Python-OR-infra-gated (mirrors pipeline_rule). Body covers Docker
#     / YAML / TOML / JSON, so it lands wherever those file types are
#     actually present.


_CLAUDE_SECURITY_RULE = """\
---
paths:
  - "**/security/**/*.py"
  - "**/auth/**/*.py"
  - "**/validators/**/*.py"
---
# Security Rules (TappsMCP)

Run `tapps_security_scan(file_path)` after editing any security-related file.

Run `tapps_consult_expert(question, domain="security")` for security design decisions.

## Mandatory Checks

- All file I/O must go through `security/path_validator.py`
- Never use `eval()`, `exec()`, or `pickle.loads()` on external input
- Never use `subprocess.run(shell=True)` with user-controlled input
- Use parameterized queries — no raw SQL string concatenation
- No hardcoded secrets, API keys, tokens, or passwords
- All retrieved content must pass through `security/content_safety.py`

## Subprocess Safety

- Only packages in `_ALLOWED_CHECKER_PACKAGES` may reach `subprocess.run`
- Always use explicit argument lists, not shell strings
- Set appropriate timeouts on all subprocess calls
"""


def generate_claude_security_rule(
    project_root: Path,
) -> dict[str, Any]:
    """Generate ``.claude/rules/security.md``.

    Path-scoped rule activated on edits to security/auth/validator files.
    Idempotent — re-running overwrites with the same content. Caller is
    expected to gate on Python signals.

    Args:
        project_root: Target project root directory.

    Returns:
        A summary dict with ``file`` and ``action``.
    """
    rules_dir = project_root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "security.md"
    existed = target.exists()
    target.write_text(_CLAUDE_SECURITY_RULE, encoding="utf-8")
    return {"file": str(target), "action": "updated" if existed else "created"}


_CLAUDE_TEST_QUALITY_RULE = """\
---
paths:
  - "tests/**/*.py"
  - "**/test_*.py"
  - "**/*_test.py"
---
# Test Quality Rules (TappsMCP)

Run `tapps_quick_check(file_path)` after editing test files.

Use `tapps_lookup_docs(library, topic)` for test framework APIs and best practices.

## Testing Standards

- Use pytest fixtures for setup/teardown, not setUp/tearDown methods
- Mock external services and I/O — never make real HTTP requests in tests
- One logical assertion per test when practical
- Use descriptive test names: `test_<what>_<condition>_<expected>`
- Use `tmp_path` fixture for temporary files, not manual cleanup
- Reset module-level caches in autouse fixtures (see conftest.py)
- Tests that depend on environment variables must use explicit fixtures

## Coverage

- New public functions need a corresponding test
- Aim for 80%+ coverage on new code
- Use `--cov-report=term-missing` to identify gaps
"""


def generate_claude_test_quality_rule(
    project_root: Path,
) -> dict[str, Any]:
    """Generate ``.claude/rules/test-quality.md``.

    Path-scoped rule activated on edits to pytest test files. Idempotent.
    Caller is expected to gate on Python signals.

    Args:
        project_root: Target project root directory.

    Returns:
        A summary dict with ``file`` and ``action``.
    """
    rules_dir = project_root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "test-quality.md"
    existed = target.exists()
    target.write_text(_CLAUDE_TEST_QUALITY_RULE, encoding="utf-8")
    return {"file": str(target), "action": "updated" if existed else "created"}


_CLAUDE_CONFIG_FILES_RULE = """\
---
paths:
  - "**/*.yaml"
  - "**/*.yml"
  - "**/*.toml"
  - "**/*.json"
  - "**/Dockerfile*"
  - "**/docker-compose*"
---
# Configuration File Rules (TappsMCP)

Run `tapps_validate_config(file_path)` when editing Dockerfile, docker-compose, or infrastructure config.

## YAML/TOML

- Use consistent indentation (2 spaces for YAML)
- Quote strings containing special characters
- Validate against known schemas when available

## Docker

- Pin base image versions (no `latest` tag)
- Use multi-stage builds for production images
- Run as non-root user
- Don't copy secrets into images

## JSON Config

- Use environment variable expansion (`${VAR}`) for secrets — never hardcode
- Add `"type"` field to MCP server entries
- Validate with `$schema` when available
"""


def generate_claude_config_files_rule(
    project_root: Path,
) -> dict[str, Any]:
    """Generate ``.claude/rules/config-files.md``.

    Path-scoped rule activated on YAML / TOML / JSON / Dockerfile edits.
    Idempotent. Caller is expected to gate on Python OR infra signals.

    Args:
        project_root: Target project root directory.

    Returns:
        A summary dict with ``file`` and ``action``.
    """
    rules_dir = project_root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    target = rules_dir / "config-files.md"
    existed = target.exists()
    target.write_text(_CLAUDE_CONFIG_FILES_RULE, encoding="utf-8")
    return {"file": str(target), "action": "updated" if existed else "created"}
