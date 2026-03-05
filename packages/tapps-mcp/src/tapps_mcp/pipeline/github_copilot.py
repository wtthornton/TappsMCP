"""GitHub Copilot agent integration generators.

Epic 21: Generate configuration files for GitHub's AI agent ecosystem —
Copilot coding agent, Copilot code review, custom agent profiles,
path-scoped instructions, and agentic workflow templates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Custom Agent Profiles (.github/agents/*.md)
# ---------------------------------------------------------------------------

_QUALITY_AGENT_PROFILE = """\
---
name: tapps-quality
description: Code quality reviewer using TappsMCP scoring and security tools
tools:
  - mcp: tapps-mcp
    tools:
      - tapps_quick_check
      - tapps_score_file
      - tapps_quality_gate
      - tapps_validate_changed
      - tapps_security_scan
---

# TappsMCP Quality Agent

You are a code quality reviewer. Use the TappsMCP MCP tools to score files,
run security scans, and enforce quality gates.

## Workflow

1. For each changed Python file, run `tapps_quick_check` first
2. If the quick check flags issues, run `tapps_score_file` for detailed scoring
3. Run `tapps_security_scan` on files touching auth, config, secrets, or user input
4. Before completing your review, run `tapps_validate_changed` with explicit `file_paths` for a final pass. Default is quick mode; only use `quick=false` as a last resort.
5. Report findings as PR review comments with severity and fix suggestions

## Standards

- Overall score must be >= 70 (standard), >= 80 (strict)
- No HIGH or CRITICAL security findings
- All new public functions must have type annotations
- Test coverage heuristic must detect corresponding test files
"""

_RESEARCHER_AGENT_PROFILE = """\
---
name: tapps-researcher
description: Technical researcher using TappsMCP expert consultation and docs
tools:
  - mcp: tapps-mcp
    tools:
      - tapps_research
      - tapps_consult_expert
      - tapps_lookup_docs
      - tapps_impact_analysis
---

# TappsMCP Research Agent

You are a technical researcher. Use the TappsMCP MCP tools to consult domain
experts, look up library documentation, and analyze change impact.

## Workflow

1. When asked about architecture or design decisions, use `tapps_consult_expert`
   with the relevant domain (security, performance, testing, database, api-design)
2. When writing code that uses third-party libraries, use `tapps_lookup_docs`
   to verify API signatures and usage patterns
3. Before refactoring, use `tapps_impact_analysis` to understand blast radius
4. For complex questions combining expert advice and documentation, use
   `tapps_research` which combines both in a single call

## Standards

- Always verify library API calls against documentation before suggesting code
- Cite the expert domain and confidence score in your responses
- Flag any impact analysis showing > 5 affected files as requiring careful review
"""

# ---------------------------------------------------------------------------
# Path-Scoped Instructions (.github/instructions/*.instructions.md)
# ---------------------------------------------------------------------------

_QUALITY_INSTRUCTIONS = """\
---
applyTo: "**/*.py"
---

# Python Quality Standards

All Python files in this project are evaluated by TappsMCP across 7 quality
categories: complexity, security, maintainability, test coverage, performance,
structure, and developer experience.

## Requirements

- Functions should have cyclomatic complexity <= 10
- No function should exceed 50 lines (excluding docstrings and blank lines)
- All public functions and methods must have type annotations
- Use `pathlib.Path` for file paths, not string concatenation
- Use `structlog` for logging, never `print()` or bare `logging`
- All file I/O must go through the path validator for sandboxing

## Security

- Never use `eval()` or `exec()` with non-literal arguments
- Never use `pickle.loads()` on untrusted data
- Never use `subprocess` with `shell=True` and user input
- Never hardcode passwords, API keys, or tokens
- Always use parameterized queries for database operations
"""

_SECURITY_INSTRUCTIONS = """\
---
applyTo: "**/security/**"
---

# Security Module Standards

Files in the security module have elevated quality requirements.

## Requirements

- All functions must have comprehensive type annotations
- Security-critical functions must have unit tests with edge cases
- No `# type: ignore` comments without an inline justification
- Input validation must occur at every external boundary
- All cryptographic operations must use well-tested libraries (not hand-rolled)
- Secret scanning patterns must cover: API keys, tokens, passwords, private keys
"""

_TESTING_INSTRUCTIONS = """\
---
applyTo: "tests/**"
---

# Testing Standards

## Requirements

- Tests must not make real HTTP requests — use mocks or `httpx.MockTransport`
- Tests must not read from or write to production configuration files
- Tests must not depend on global state without explicit setup/teardown
- Use `pytest` fixtures for shared setup, not `setUp()`/`tearDown()` methods
- Use `tmp_path` fixture for any file I/O in tests
- Tests should be deterministic — no random data without fixed seeds
- Mark slow tests (> 5 seconds) with `@pytest.mark.slow`
"""

# ---------------------------------------------------------------------------
# Enhanced Copilot Instructions (.github/copilot-instructions.md)
# ---------------------------------------------------------------------------

_ENHANCED_COPILOT_INSTRUCTIONS = """\
# Copilot Instructions

This project uses **TappsMCP** (Code Quality MCP Server) for automated
quality analysis. When TappsMCP is available as an MCP server, follow
the pipeline below.

## TappsMCP Quality Pipeline

### Stage 1: Discover
- Run `tapps_session_start` at the beginning of each session
- Use `tapps_project_profile` to understand the tech stack

### Stage 2: Research
- Use `tapps_lookup_docs` to verify library API signatures
- Use `tapps_consult_expert` for architecture/security decisions
- Use `tapps_impact_analysis` before refactoring

### Stage 3: Develop
- After editing Python files, run `tapps_quick_check`
- If quick check flags issues, run `tapps_score_file` for details
- Fix issues before moving to the next file

### Stage 4: Validate
- Run `tapps_validate_changed` with explicit `file_paths` before declaring work complete (default is quick mode; `quick=false` is a last resort)
- Run `tapps_security_scan` on security-sensitive files
- Ensure overall score >= 70 and no HIGH security findings

### Stage 5: Verify
- Run `tapps_quality_gate` for pass/fail verdict
- Run `tapps_checklist` to confirm all steps were completed

## Code Standards

- Python 3.12+ with `from __future__ import annotations`
- Type annotations on all functions (`mypy --strict`)
- `structlog` for logging, `pathlib.Path` for file paths
- `ruff` for linting and formatting (line length: 100)
- All file operations through the path validator
"""

# ---------------------------------------------------------------------------
# Agentic Workflow Templates (opt-in, technical preview)
# ---------------------------------------------------------------------------

_AGENTIC_PR_REVIEW = """\
# .github/workflows/agentic-pr-review.yml
# Generated by TappsMCP tapps_init — agentic workflow (technical preview)
# Requires GitHub Agentic Workflows to be enabled for the repository.
name: Agentic PR Quality Review

on:
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write

jobs:
  quality-review:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install tools
        run: |
          pip install tapps-mcp ruff mypy bandit radon vulture

      - name: Run quality analysis on changed files
        env:
          TAPPS_MCP_PROJECT_ROOT: ${{ github.workspace }}
        run: |
          tapps-mcp validate-changed --preset strict
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_agent_profiles(project_root: Path) -> dict[str, Any]:
    """Generate custom Copilot agent profiles in ``.github/agents/``.

    Creates ``tapps-quality.md`` and ``tapps-researcher.md`` with
    YAML frontmatter specifying tools and MCP server config.

    Returns a summary dict with ``files`` and ``action``.
    """
    agents_dir = project_root / ".github" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []
    profiles = {
        "tapps-quality.md": _QUALITY_AGENT_PROFILE,
        "tapps-researcher.md": _RESEARCHER_AGENT_PROFILE,
    }

    for filename, content in profiles.items():
        target = agents_dir / filename
        target.write_text(content, encoding="utf-8")
        files_written.append(str(target.relative_to(project_root)))

    return {"files": files_written, "action": "created", "count": len(files_written)}


def generate_path_scoped_instructions(project_root: Path) -> dict[str, Any]:
    """Generate path-scoped instruction files in ``.github/instructions/``.

    Creates ``quality.instructions.md``, ``security.instructions.md``,
    and ``testing.instructions.md`` with YAML frontmatter specifying
    ``applyTo`` glob patterns.

    Returns a summary dict with ``files`` and ``action``.
    """
    instructions_dir = project_root / ".github" / "instructions"
    instructions_dir.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []
    instructions = {
        "quality.instructions.md": _QUALITY_INSTRUCTIONS,
        "security.instructions.md": _SECURITY_INSTRUCTIONS,
        "testing.instructions.md": _TESTING_INSTRUCTIONS,
    }

    for filename, content in instructions.items():
        target = instructions_dir / filename
        target.write_text(content, encoding="utf-8")
        files_written.append(str(target.relative_to(project_root)))

    return {"files": files_written, "action": "created", "count": len(files_written)}


def generate_enhanced_copilot_instructions(project_root: Path) -> dict[str, Any]:
    """Generate enhanced ``.github/copilot-instructions.md``.

    Replaces the basic instructions with ones that include the full
    TappsMCP pipeline stages and concrete tool call sequences.

    Returns a summary dict with ``file`` and ``action``.
    """
    github_dir = project_root / ".github"
    github_dir.mkdir(parents=True, exist_ok=True)
    target = github_dir / "copilot-instructions.md"
    existed = target.exists()
    target.write_text(_ENHANCED_COPILOT_INSTRUCTIONS, encoding="utf-8")
    return {
        "file": str(target.relative_to(project_root)),
        "action": "updated" if existed else "created",
    }


def generate_agentic_workflow(project_root: Path) -> dict[str, Any]:
    """Generate agentic PR review workflow (technical preview).

    Creates ``.github/workflows/agentic-pr-review.yml``. This workflow
    requires GitHub Agentic Workflows to be enabled for the repository.

    Returns a summary dict with ``file`` and ``action``.
    """
    wf_dir = project_root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    target = wf_dir / "agentic-pr-review.yml"
    target.write_text(_AGENTIC_PR_REVIEW, encoding="utf-8")
    return {"file": str(target.relative_to(project_root)), "action": "created"}


def generate_all_copilot_config(project_root: Path) -> dict[str, Any]:
    """Generate all Copilot agent configuration files.

    Convenience function that calls all individual generators.

    Returns a summary dict with sub-results.
    """
    results: dict[str, Any] = {}
    results["agent_profiles"] = generate_agent_profiles(project_root)
    results["path_instructions"] = generate_path_scoped_instructions(project_root)
    results["copilot_instructions"] = generate_enhanced_copilot_instructions(project_root)
    results["agentic_workflow"] = generate_agentic_workflow(project_root)

    total_files = (
        results["agent_profiles"]["count"]
        + results["path_instructions"]["count"]
        + 1  # copilot-instructions.md
        + 1  # agentic workflow
    )
    results["total_files"] = total_files
    results["success"] = True
    return results
