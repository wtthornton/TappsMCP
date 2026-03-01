"""Plugin bundle generators and miscellaneous platform generators.

Contains plugin bundle generation (Claude + Cursor), Cursor rules,
agent teams hooks, Copilot instructions, BugBot rules, and CI workflow.
Extracted from ``platform_generators.py`` to reduce file size.
"""

from __future__ import annotations

import base64
import json
import stat
from typing import TYPE_CHECKING, Any

from tapps_mcp.pipeline.platform_hook_templates import (
    AGENT_TEAMS_HOOKS_CONFIG,
    AGENT_TEAMS_HOOK_SCRIPTS,
    AGENT_TEAMS_CLAUDE_MD_SECTION,
    CLAUDE_HOOKS_CONFIG,
    CLAUDE_HOOK_SCRIPTS,
    CURSOR_HOOKS_CONFIG,
    CURSOR_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS, CURSOR_SKILLS
from tapps_mcp.pipeline.platform_subagents import CLAUDE_AGENTS, CURSOR_AGENTS

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Cursor rule types (Story 12.11)
# ---------------------------------------------------------------------------

_CURSOR_RULE_PIPELINE = """\
---
alwaysApply: true
---

# TAPPS Quality Pipeline

This project uses the TAPPS MCP server for code quality enforcement.

## Session Start (REQUIRED)

Call `tapps_session_start()` as the FIRST action in every session.
Then call `tapps_memory(action="search", query="...")` to recall past decisions.

## After Editing Python Files (REQUIRED)

Call `tapps_quick_check(file_path)` after editing any Python file.

## Before Declaring Work Complete (BLOCKING)

Call `tapps_validate_changed()` to batch-validate all changed files.
The quality gate MUST pass before work is declared complete.
Call `tapps_checklist(task_type)` as the FINAL verification step.
"""

_CURSOR_RULE_PYTHON_QUALITY = """\
---
globs: "*.py"
alwaysApply: false
---

# Python Quality Standards

When Python files are referenced, enforce these quality standards:

## 7 Scoring Categories

TappsMCP scores Python code across 7 categories (0-100 each):

1. **Complexity** - Cyclomatic complexity (radon cc / AST fallback)
2. **Security** - Bandit + pattern heuristics
3. **Maintainability** - Maintainability index (radon mi / AST fallback)
4. **Test Coverage** - Heuristic from matching test file existence
5. **Performance** - Nested loops, large functions, deep nesting
6. **Structure** - Project layout (pyproject.toml, tests/, README, .git)
7. **DevEx** - Developer experience (docs, AGENTS.md, tooling config)

## Actions

- Call `tapps_quick_check(file_path)` on edited Python files
- Any category scoring below 70 needs immediate attention
- Call `tapps_score_file(file_path)` for full breakdown
"""

_CURSOR_RULE_EXPERT = """\
---
description: >-
  TappsMCP domain expert consultation - use when needing
  guidance on security, performance, architecture, testing,
  or other domain-specific best practices.
---

# Expert Consultation

Call `tapps_consult_expert(question)` for domain guidance.

## Available Expert Domains (17)

- security, performance-optimization, testing-strategies, code-quality-analysis
- software-architecture, development-workflow, data-privacy-compliance
- accessibility, user-experience, documentation-knowledge-management
- ai-frameworks, agent-learning, observability-monitoring
- api-design-integration, cloud-infrastructure, database-data-management, github

## Usage

Provide a clear question and optionally specify the domain:

```
tapps_consult_expert(
    question="How should I handle auth tokens?",
    domain="security"
)
```

Returns RAG-backed expert guidance with confidence scores.
"""


def generate_cursor_rules(project_root: Path) -> dict[str, Any]:
    """Generate three Cursor rule files with different rule types.

    Creates ``.cursor/rules/`` with:
    - ``tapps-pipeline.mdc`` (alwaysApply)
    - ``tapps-python-quality.mdc`` (autoAttach via globs)
    - ``tapps-expert-consultation.mdc`` (agentRequested via description)

    Returns a summary dict with ``created`` and ``skipped`` lists.
    """
    rules_dir = project_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)

    rules: dict[str, str] = {
        "tapps-pipeline.mdc": _CURSOR_RULE_PIPELINE,
        "tapps-python-quality.mdc": _CURSOR_RULE_PYTHON_QUALITY,
        "tapps-expert-consultation.mdc": _CURSOR_RULE_EXPERT,
    }

    created: list[str] = []
    skipped: list[str] = []
    for name, content in rules.items():
        target = rules_dir / name
        if target.exists():
            skipped.append(name)
        else:
            target.write_text(content, encoding="utf-8")
            created.append(name)

    return {"created": created, "skipped": skipped}


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
    rules = {
        "tapps-pipeline.mdc": _CURSOR_RULE_PIPELINE,
        "tapps-python-quality.mdc": _CURSOR_RULE_PYTHON_QUALITY,
        "tapps-expert-consultation.mdc": _CURSOR_RULE_EXPERT,
    }
    for name, content in rules.items():
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
# VS Code / Copilot Instructions (Story 12.13)
# ---------------------------------------------------------------------------

_COPILOT_INSTRUCTIONS = """\
# TappsMCP Quality Tools

This project uses TappsMCP for code quality analysis. When TappsMCP is
available as an MCP server (configured in `.vscode/mcp.json`), use the
following tools to maintain code quality throughout development.

## Key Tools

- `tapps_session_start` - Initialize a TappsMCP session at the start of
  each work session. Call this first.
- `tapps_quick_check` - Run a quick quality check on a single file after
  editing. Returns score and top issues.
- `tapps_quality_gate` - Run a pass/fail quality gate against a configurable
  preset (development, staging, or production).
- `tapps_validate_changed` - Validate all changed files against the quality
  gate. Call this before declaring work complete.
- `tapps_consult_expert` - Consult a domain expert (security, performance,
  architecture, testing, and more) for guidance.
- `tapps_score_file` - Get a detailed 7-category quality score for any file.

## Workflow

1. Start a session: call `tapps_session_start`
2. After editing Python files: call `tapps_quick_check` on changed files
3. Before creating a PR or declaring work complete: call
   `tapps_validate_changed`
4. For domain-specific guidance: call `tapps_consult_expert` with the
   relevant domain

## Quality Scoring Categories

TappsMCP scores code across 7 categories (0-100 each):
correctness, security, maintainability, performance, documentation,
testing, and style.
"""


def generate_copilot_instructions(project_root: Path) -> dict[str, Any]:
    """Generate ``.github/copilot-instructions.md`` for VS Code Copilot.

    Creates the ``.github/`` directory if it does not exist and writes
    the instructions file. Idempotent - re-running overwrites with the
    same content.

    Returns a summary dict with ``file`` and ``action``.
    """
    github_dir = project_root / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    target = github_dir / "copilot-instructions.md"
    target.write_text(_COPILOT_INSTRUCTIONS, encoding="utf-8")
    return {"file": str(target), "action": "created"}


# ---------------------------------------------------------------------------
# Cursor BugBot rules (Story 12.14)
# ---------------------------------------------------------------------------

_BUGBOT_RULES = """\
# TappsMCP Quality Standards for BugBot

This project uses TappsMCP (Code Quality MCP Server) for automated quality
analysis. The following standards are enforced during PR review.

## Code Quality Standards

All Python files must meet TappsMCP scoring thresholds:
- Overall score: >= 70 (development), >= 80 (staging), >= 90 (production)
- No individual category score below 50

### Scoring Categories

| Category | What BugBot Should Check |
|----------|-------------------------|
| Correctness | Logic errors, unchecked return values, unreachable code |
| Security | Hardcoded secrets, unsafe deserialization, injection vulns |
| Maintainability | Functions > 50 lines, cyclomatic complexity > 10 |
| Performance | Nested loops on large data, sync I/O in async context |
| Documentation | Missing docstrings on public API, outdated params |
| Testing | Functions without test coverage, real external service calls |
| Style | Inconsistent naming, bare `except`, missing type annotations |

## Security Requirements

Flag any of the following as blocking issues:
- Hardcoded passwords, API keys, tokens, or secrets
- Use of `eval()` or `exec()` with non-literal arguments
- `pickle.loads()` on data from external sources
- Raw SQL string concatenation (use parameterized queries)
- File path operations without validation against allowed base dir
- `subprocess` calls with `shell=True` and interpolated user input

## Python Style Rules

Flag the following as non-blocking warnings:
- Public functions and methods without type annotations
- Public classes and functions without docstrings
- Bare `except:` clauses (must specify exception type)
- Functions with cyclomatic complexity > 10
- Functions longer than 50 lines (excluding docstrings/blanks)
- Mutable default arguments in function signatures

## Testing Requirements

Flag the following as non-blocking warnings:
- New public functions without a corresponding test in `tests/`
- Tests that make real HTTP requests without mocking
- Tests that read from or write to production configuration files
- Tests that depend on environment variables without explicit fixtures

## Directory Hierarchy

This `BUGBOT.md` applies to all files in `.cursor/` and subdirectories.
Place a subdirectory `BUGBOT.md` to override these rules for specific
sub-packages with different thresholds.
"""


def generate_bugbot_rules(project_root: Path) -> dict[str, Any]:
    """Generate ``.cursor/BUGBOT.md`` for Cursor BugBot PR reviews.

    Creates the ``.cursor/`` directory if needed and writes the rules
    file. Idempotent - re-running overwrites with the same content.

    Returns a summary dict with ``file`` and ``action``.
    """
    cursor_dir = project_root / ".cursor"
    cursor_dir.mkdir(parents=True, exist_ok=True)
    target = cursor_dir / "BUGBOT.md"
    target.write_text(_BUGBOT_RULES, encoding="utf-8")
    return {"file": str(target), "action": "created"}


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
