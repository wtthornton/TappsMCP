# Documentation Strategy for Python Projects

## Overview

Effective documentation is a force multiplier for software teams. This guide covers
Python docstring standards, README templates, CHANGELOG patterns, API documentation
generation, documentation tooling, and knowledge base management strategies.

## Python Docstring Standards

### Google Style (Recommended)

Google-style docstrings are concise, readable, and well-supported by Sphinx and MkDocs:

```python
def score_file(
    file_path: str,
    quick: bool = False,
    fix: bool = False,
) -> dict[str, float]:
    """Score a Python file across seven quality categories.

    Runs ruff (and optionally mypy, bandit, radon) to produce a normalized
    quality score between 0 and 100.

    Args:
        file_path: Absolute path to the Python file.
        quick: If True, run ruff-only scoring for speed.
        fix: If True, apply ruff auto-fixes before scoring.

    Returns:
        A dict mapping category names to float scores, plus an
        ``overall_score`` key with the weighted average.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        PermissionError: If *file_path* is outside the project sandbox.

    Example:
        >>> result = score_file("/src/main.py", quick=True)
        >>> assert 0 <= result["overall_score"] <= 100
    """
```

### NumPy Style

NumPy style uses section headers with underlines. Preferred in scientific computing:

```python
def compute_metrics(data: list[float]) -> dict[str, float]:
    """
    Compute descriptive statistics for a numeric dataset.

    Parameters
    ----------
    data : list[float]
        Input values. Must contain at least one element.

    Returns
    -------
    dict[str, float]
        Keys: ``mean``, ``median``, ``std_dev``, ``min``, ``max``.

    Raises
    ------
    ValueError
        If *data* is empty.
    """
```

### Docstring Coverage Enforcement

Use `interrogate` to enforce docstring coverage in CI:

```toml
# pyproject.toml
[tool.interrogate]
ignore-init-method = true
ignore-init-module = true
ignore-magic = true
ignore-semiprivate = false
fail-under = 80
verbose = 1
exclude = ["tests", "docs"]
```

### Module-Level Docstrings

Every module should have a docstring explaining its purpose and public API:

```python
"""SQLite-backed persistence layer for the shared memory subsystem.

Uses WAL journal mode for concurrent reads during writes, FTS5 for
full-text search, and schema versioning with forward migrations.
A JSONL audit log is maintained for debugging and compliance.
"""
```

## README Templates

### Minimal README Structure

```markdown
# Project Name

One-line description of what the project does.

## Installation

pip install project-name

## Quick Start

Minimal working example.

## Documentation

Link to full docs.

## License

MIT
```

### Comprehensive README Structure

A well-structured README includes these sections in order:

1. **Title and badges** - project name, CI status, version, coverage
2. **Description** - one paragraph explaining what and why
3. **Features** - bullet list of key capabilities
4. **Installation** - pip/uv/conda install instructions
5. **Quick start** - minimal working code example
6. **Configuration** - environment variables, config files
7. **Usage** - detailed examples for common use cases
8. **API reference** - link to generated docs
9. **Architecture** - high-level component diagram
10. **Contributing** - development setup, testing, PR guidelines
11. **License** - SPDX identifier

### Badge Templates

```markdown
[![CI](https://github.com/org/repo/actions/workflows/ci.yml/badge.svg)](link)
[![Coverage](https://codecov.io/gh/org/repo/branch/main/graph/badge.svg)](link)
[![PyPI](https://img.shields.io/pypi/v/package-name)](link)
[![Python](https://img.shields.io/pypi/pyversions/package-name)](link)
```

## CHANGELOG Patterns

### Keep a Changelog Format

Follow the Keep a Changelog specification (keepachangelog.com):

```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- New `tapps_memory` tool for cross-session knowledge sharing

### Changed
- Improved `tapps_quick_check` with AST complexity heuristic

### Fixed
- Cache reset race condition in concurrent test runs

## [1.2.0] - 2026-02-15

### Added
- Expert knowledge enhancement (Epic 26)
- Memory persistence with SQLite WAL mode
```

### Change Categories

Use exactly these six categories (in this order):

1. **Added** - new features
2. **Changed** - changes in existing functionality
3. **Deprecated** - soon-to-be removed features
4. **Removed** - removed features
5. **Fixed** - bug fixes
6. **Security** - vulnerability fixes

### Automated Changelog Generation

Use `git-cliff` or `towncrier` for automated changelog generation:

```python
# pyproject.toml (towncrier)
[tool.towncrier]
package = "tapps_mcp"
directory = "changes"
filename = "CHANGELOG.md"
title_format = "## [{version}] - {project_date}"

[[tool.towncrier.type]]
directory = "feature"
name = "Added"
showcontent = true

[[tool.towncrier.type]]
directory = "bugfix"
name = "Fixed"
showcontent = true
```

## API Documentation Generation

### MkDocs with Material Theme

MkDocs Material is the recommended documentation framework for Python projects:

```yaml
# mkdocs.yml
site_name: TappsMCP Documentation
theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - search.suggest
    - content.code.copy

plugins:
  - search
  - mkdocstrings:
      handlers:
        python:
          options:
            show_source: true
            show_root_heading: true
            members_order: source

nav:
  - Home: index.md
  - Getting Started: getting-started.md
  - API Reference:
    - Scoring: api/scoring.md
    - Security: api/security.md
    - Experts: api/experts.md
  - Architecture: architecture.md
```

### mkdocstrings Configuration

Auto-generate API docs from docstrings:

```markdown
<!-- docs/api/scoring.md -->
# Scoring API

::: tapps_mcp.scoring.scorer.CodeScorer
    options:
      show_root_heading: true
      members:
        - score_file
        - score_quick
```

### Sphinx Setup (Alternative)

For projects requiring Sphinx compatibility:

```python
# docs/conf.py
project = "TappsMCP"
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
]
autodoc_typehints = "description"
napoleon_google_docstring = True
```

## Documentation as Code

### Docs in CI/CD

Validate documentation in CI to prevent broken links and outdated content:

```yaml
# .github/workflows/docs.yml
name: Documentation
on: [push, pull_request]
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install mkdocs-material mkdocstrings[python]
      - run: mkdocs build --strict
```

### Link Validation

Check for broken links in documentation:

```python
# pyproject.toml
[tool.linkchecker]
check_internal = true
check_external = true
ignore_urls = ["https://localhost"]
```

### Doc Testing with doctest

Embed testable examples in docstrings:

```python
def calculate_score(raw: float, max_score: float = 100.0) -> float:
    """Normalize a raw score to a 0-100 scale.

    >>> calculate_score(42.0, 100.0)
    42.0
    >>> calculate_score(7.5, 10.0)
    75.0
    >>> calculate_score(0.0, 50.0)
    0.0
    """
    if max_score <= 0:
        return 0.0
    return min((raw / max_score) * 100.0, 100.0)
```

Run doctests in CI:

```bash
python -m pytest --doctest-modules src/
```

## Knowledge Base Management

### Structured Knowledge Files

Organize domain expertise in markdown files with consistent structure:

```markdown
# Topic Title

## Overview
Brief description of the topic and its relevance.

## Key Concepts
Core ideas practitioners need to understand.

## Patterns and Practices
Concrete, actionable patterns with code examples.

## Anti-Patterns
Common mistakes and how to avoid them.

## References
Links to authoritative sources.
```

### Knowledge File Conventions

1. **One topic per file** - keep files focused and searchable
2. **Descriptive filenames** - use kebab-case slugs (e.g., `mcp-server-architecture.md`)
3. **Minimum 200 lines** - ensure sufficient depth for expert guidance
4. **Code examples required** - every pattern should include a working example
5. **No stubs** - delete placeholder files, create real content or nothing

### Knowledge Freshness Tracking

Track when knowledge files were last verified:

```python
from datetime import datetime, timedelta

FRESHNESS_THRESHOLD = timedelta(days=90)

def is_stale(last_verified: datetime) -> bool:
    """Check if a knowledge file needs review."""
    return datetime.now() - last_verified > FRESHNESS_THRESHOLD
```

### Knowledge Validation

Validate knowledge files programmatically:

```python
import ast

def validate_knowledge_file(content: str) -> list[str]:
    """Validate a knowledge markdown file for quality issues."""
    issues = []

    # Check H1 title
    lines = content.strip().splitlines()
    if not lines or not lines[0].startswith("# "):
        issues.append("Missing H1 title on first line")

    # Check code blocks are closed
    in_code = False
    for i, line in enumerate(lines, 1):
        if line.startswith("```"):
            in_code = not in_code
    if in_code:
        issues.append("Unclosed code block")

    # Validate Python code blocks parse
    blocks = extract_python_blocks(content)
    for block_num, code in enumerate(blocks, 1):
        try:
            ast.parse(code)
        except SyntaxError as e:
            issues.append(f"Python block {block_num}: {e.msg}")

    return issues


def extract_python_blocks(content: str) -> list[str]:
    """Extract Python code blocks from markdown."""
    blocks = []
    current_block: list[str] = []
    in_python = False

    for line in content.splitlines():
        if line.startswith("```python"):
            in_python = True
            current_block = []
        elif line.startswith("```") and in_python:
            in_python = False
            blocks.append("\n".join(current_block))
        elif in_python:
            current_block.append(line)

    return blocks
```

## AGENTS.md and AI-Facing Documentation

### Purpose

AGENTS.md provides instructions to AI coding assistants about project conventions,
tool usage, and workflow expectations. It is distinct from developer documentation.

### Structure

```markdown
# AGENTS.md

## Project Overview
What the project does and key architectural decisions.

## Development Commands
How to install, test, lint, and run.

## Code Conventions
Naming, formatting, type checking expectations.

## Tool Usage
MCP tools available, when to call each, required sequences.

## Known Gotchas
Tricky behaviors that trip up both humans and AI.
```

### Key Principles

1. **Be prescriptive** - tell the AI what to do, not just what exists
2. **Include examples** - show exact command invocations and code patterns
3. **Document gotchas** - call out non-obvious behaviors explicitly
4. **Keep current** - update when adding tools, changing conventions
5. **Engagement levels** - vary strictness (high/medium/low) by project needs

## Versioned Documentation

### Docs Alongside Code

Keep documentation versioned with the codebase:

```
project/
  docs/
    index.md
    getting-started.md
    api/
      scoring.md
      security.md
    architecture.md
  src/
    tapps_mcp/
  mkdocs.yml
  CHANGELOG.md
  README.md
```

### Documentation Review in PRs

Include documentation changes in code review:

```yaml
# .github/CODEOWNERS
/docs/     @team-docs-reviewers
README.md  @team-docs-reviewers
CHANGELOG.md @team-lead
```

## Anti-Patterns

### Documentation Rot

- Writing docs once and never updating them
- Fix: tie doc updates to feature PRs, validate in CI

### Over-Documentation

- Documenting obvious code with redundant comments
- Fix: document the why, not the what; let code speak for itself

### Missing API Examples

- Providing API reference without usage examples
- Fix: require at least one example per public function

### Orphaned Documentation

- Docs that reference deleted code or outdated APIs
- Fix: use link checkers and doc build validation in CI

## Quick Reference

| Aspect | Recommendation |
|---|---|
| Docstring style | Google (or NumPy for scientific) |
| Doc framework | MkDocs Material + mkdocstrings |
| Changelog format | Keep a Changelog |
| Coverage tool | interrogate (80% minimum) |
| CI validation | mkdocs build --strict |
| Knowledge files | 200+ lines, code examples, no stubs |
| AGENTS.md | Prescriptive, engagement-leveled |
