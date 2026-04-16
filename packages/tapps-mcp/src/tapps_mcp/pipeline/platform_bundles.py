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
    SUPPORTED_CLAUDE_HOOK_KEYS,
)
from tapps_mcp.pipeline.platform_rules import (
    CURSOR_RULE_TEMPLATES,
)
from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS, CURSOR_SKILLS
from tapps_mcp.pipeline.platform_subagents import CLAUDE_AGENTS, CURSOR_AGENTS

if TYPE_CHECKING:
    from pathlib import Path


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
        k: v for k, v in config["hooks"].items() if k in SUPPORTED_CLAUDE_HOOK_KEYS
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
) -> dict[str, Any]:
    """Generate a Claude Code plugin bundle directory.

    Creates the full plugin directory structure under *output_dir*
    including plugin.json, agents, skills, hooks, .mcp.json,
    and README.md.

    Returns a summary dict with ``files_created``.
    """
    files_created: list[str] = []

    # .claude-plugin/plugin.json
    meta_dir = output_dir / ".claude-plugin"
    meta_dir.mkdir(parents=True, exist_ok=True)
    plugin_data = {
        "name": "tapps-mcp",
        "version": version,
        "description": (
            "Code quality scoring, security scanning, and quality gates for Python projects"
        ),
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
    for event, entries in CLAUDE_HOOKS_CONFIG.items():
        plugin_entries = []
        for entry in entries:
            pe: dict[str, Any] = {}
            if "matcher" in entry:
                pe["matcher"] = entry["matcher"]
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

    # .mcp.json
    mcp_config = {
        "mcpServers": {
            "tapps-mcp": {
                "command": "uvx",
                "args": ["tapps-mcp", "serve"],
                "env": {
                    "TAPPS_MCP_PROJECT_ROOT": ".",
                },
            },
        },
    }
    (output_dir / ".mcp.json").write_text(
        json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8"
    )
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
        event: [
            {"command": cmd["command"].replace(".cursor/hooks/", "hooks/")}
            for cmd in cmds
        ]
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
    (output_dir / "mcp.json").write_text(
        json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8"
    )
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
# CI / Headless workflow (Story 12.16)
# ---------------------------------------------------------------------------

_CI_WORKFLOW = """\
# .github/workflows/tapps-quality.yml
# Generated by TappsMCP tapps_init - edit as needed
name: TappsMCP Quality Gate

on:
  pull_request:
    paths:
      - "**.py"

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install TappsMCP
        run: pip install tapps-mcp

      - name: Run TappsMCP quality gate
        env:
          TAPPS_MCP_PROJECT_ROOT: ${{ github.workspace }}
        run: |
          tapps-mcp validate-changed \\
            --preset staging
"""

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


def generate_ci_workflow(project_root: Path) -> dict[str, Any]:
    """Generate ``.github/workflows/tapps-quality.yml`` GitHub Actions workflow.

    Creates the ``.github/workflows/`` directory if needed and writes the
    workflow file. Idempotent - re-running overwrites with same content.

    Returns a summary dict with ``file`` and ``action``.
    """
    wf_dir = project_root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    target = wf_dir / "tapps-quality.yml"
    target.write_text(_CI_WORKFLOW, encoding="utf-8")
    return {"file": str(target), "action": "created"}


def get_ci_claude_md_section() -> str:
    """Return the CI Integration documentation section for CLAUDE.md."""
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
