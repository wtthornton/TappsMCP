"""Rule and instruction generators for Cursor, Copilot, and BugBot.

Contains Cursor rule file generation, VS Code Copilot instructions,
and BugBot PR review rules. Extracted from ``platform_bundles.py``
to reduce file size.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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

Call `tapps_validate_changed(file_paths="file1.py,file2.py")` with explicit paths to batch-validate changed files. **Never call without `file_paths`** - auto-detect scans all git-changed files and can be very slow. Default is quick mode; only use `quick=false` as a last resort.
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
5. **Performance** - Halstead metrics, perflint anti-patterns, nested loops, large functions, deep nesting
6. **Structure** - Project layout (pyproject.toml, tests/, README, .git)
7. **DevEx** - Developer experience (docs, AGENTS.md, tooling config)

## Actions

- Call `tapps_quick_check(file_path)` on edited Python files
- Use `tapps_lookup_docs(library, topic)` before using unfamiliar library APIs
- Run `tapps_security_scan(file_path)` on security-sensitive changes
- Any category scoring below 70 needs immediate attention
- Call `tapps_score_file(file_path)` for full breakdown
"""

_CURSOR_RULE_EXPERT = """\
---
description: >-
  TappsMCP library documentation lookup - use when needing
  documentation, API references, or usage examples for
  external libraries and frameworks.
---

# Library Documentation Lookup

Call `tapps_lookup_docs(library, topic)` to look up library documentation.

## Usage

Provide the library name and an optional topic:

```
tapps_lookup_docs(
    library="httpx",
    topic="async client"
)
```

Returns documentation excerpts and API references for the specified library.
"""

_CURSOR_RULE_AGENT_SCOPE = """\
---
alwaysApply: true
---

# Deployed Agent Scope (TappsMCP)

Agents deployed by `tapps_init` / `tapps_upgrade` must stay scoped to THIS
repo and THIS project for any **write** operation.

## Allowed (read)

- Documentation lookups across any project.
- Searching memory across federated projects to inform decisions.
- Browsing sibling repositories for reference only.

## Forbidden (write outside the deploying project)

- Creating, updating, commenting on, or moving Linear (or other tracker)
  issues that belong to a different project than this repo.
- Modifying files, branches, or pull requests in any other repository.
- Pushing, merging, releasing, or running automation for another project.

## How to apply

- Read team / project / repo identity from `.tapps-mcp.yaml` or the current
  git remote, NOT from arbitrary search results that may point at other
  workspaces.
- When in doubt whether a target belongs to this project, stop and ask the
  user instead of writing.
"""

# Make rule templates accessible for plugin bundle generation
CURSOR_RULE_TEMPLATES: dict[str, str] = {
    "tapps-pipeline.mdc": _CURSOR_RULE_PIPELINE,
    "tapps-python-quality.mdc": _CURSOR_RULE_PYTHON_QUALITY,
    "tapps-expert-consultation.mdc": _CURSOR_RULE_EXPERT,
    "tapps-agent-scope.mdc": _CURSOR_RULE_AGENT_SCOPE,
}


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

    created: list[str] = []
    skipped: list[str] = []
    for name, content in CURSOR_RULE_TEMPLATES.items():
        target = rules_dir / name
        if target.exists():
            skipped.append(name)
        else:
            target.write_text(content, encoding="utf-8")
            created.append(name)

    return {"created": created, "skipped": skipped}


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
- `tapps_lookup_docs` - Look up library documentation and API references
  for external libraries and frameworks.
- `tapps_score_file` - Get a detailed 7-category quality score for any file.

## Workflow

1. Start a session: call `tapps_session_start`
2. After editing Python files: call `tapps_quick_check` on changed files
3. Before creating a PR or declaring work complete: call
   `tapps_validate_changed`
4. For library documentation: call `tapps_lookup_docs` with the
   library name and topic

## Quality Scoring Categories

TappsMCP scores code across 7 categories (0-100 each):
correctness, security, maintainability, performance, documentation,
testing, and style.

## Project Scope (do not break out of this repo/project)

This Copilot instance was configured for THIS repo by `tapps_init` /
`tapps_upgrade`. Reading docs across projects is fine; **writing** outside
this repo or the linked tracker project is not. Specifically:

- Do not create, update, comment on, or move issues that belong to a
  different project than this repo.
- Do not modify files, branches, or pull requests in any other repository.
- Read team / project identity from `.tapps-mcp.yaml` or the current git
  remote, not from arbitrary search results.
- If a task seems to require a write outside this repo/project, ask the
  user before proceeding.
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

## Cross-Project Write Boundary

BugBot must not file issues, leave comments, or trigger automation in any
project other than the one this PR belongs to. Reads across projects are
fine. If a finding implies a change in another repo or tracker project,
flag it in this PR's review instead of acting on it directly.
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
