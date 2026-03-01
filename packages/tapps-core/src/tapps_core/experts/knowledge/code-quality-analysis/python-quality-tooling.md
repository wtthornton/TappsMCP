# Python Quality Tooling

## Overview

This guide covers the Python quality tooling ecosystem: ruff for linting and
formatting, mypy for type checking, bandit for security scanning, radon for
complexity metrics, vulture for dead code detection, and pre-commit integration.
All tools are used by TappsMCP's scoring pipeline to produce deterministic
quality assessments.

## Ruff (v0.15+)

### What is Ruff?

Ruff is an extremely fast Python linter and formatter written in Rust. It
replaces flake8, isort, pyflakes, pycodestyle, pydocstyle, and more with
a single tool that runs 10-100x faster than alternatives.

### Basic Configuration

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "A",    # flake8-builtins
    "C4",   # flake8-comprehensions
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
    "RUF",  # ruff-specific rules
    "S",    # flake8-bandit (security)
    "ANN",  # flake8-annotations
    "PT",   # flake8-pytest-style
    "PL",   # pylint
]
ignore = [
    "PLR0913",  # too-many-arguments (inherent to dispatch functions)
    "PLR0912",  # too-many-branches
    "ANN101",   # removed in newer ruff versions
    "ANN102",   # removed in newer ruff versions
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "ANN"]  # allow assert, skip annotations in tests
```

### Rule Selection Strategy

Start with a broad rule set and ignore specific rules as needed:

```toml
# Tier 1: Always enable (catches real bugs)
select = ["E", "F", "W", "B", "UP", "I"]

# Tier 2: Add for code quality (enable after initial cleanup)
# "N", "SIM", "C4", "RUF", "TCH"

# Tier 3: Add for strictness (enable for mature projects)
# "ANN", "S", "PL", "PT"
```

### Common Ruff Gotchas

**RUF001 - Ambiguous Unicode characters:**

```python
# BAD - en-dash triggers RUF001
description = "10-100x faster"  # ruff flags the en-dash

# GOOD - use plain hyphen
description = "10-100x faster"
```

**RUF012 - Mutable class-level attributes:**

```python
from typing import ClassVar

class Config:
    # BAD - mutable default without ClassVar
    allowed_hosts: list[str] = []

    # GOOD - annotate with ClassVar
    allowed_hosts: ClassVar[list[str]] = []
```

**TCH003 - TYPE_CHECKING imports vs runtime:**

```python
from __future__ import annotations
from typing import TYPE_CHECKING

# If Path is only used in annotations, move to TYPE_CHECKING
if TYPE_CHECKING:
    from pathlib import Path

# If Path is used as a constructor (Path("foo")), keep at runtime
from pathlib import Path
```

### Ruff Auto-Fix

Ruff can automatically fix many issues:

```bash
# Fix all auto-fixable issues
ruff check --fix src/

# Format code
ruff format src/

# Check formatting without modifying
ruff format --check src/
```

### Ruff in CI

```yaml
steps:
  - name: Ruff lint
    run: ruff check src/ --output-format=github
  - name: Ruff format
    run: ruff format --check src/
```

## mypy (v1.19+ Strict Mode)

### Strict Configuration

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
show_error_codes = true

# Module-specific overrides
[[tool.mypy.overrides]]
module = "tapps_mcp.server"
disallow_untyped_decorators = false  # @mcp.tool() is untyped

[[tool.mypy.overrides]]
module = [
    "mcp",
    "mcp.*",
    "faiss",
    "numpy",
    "sentence_transformers",
    "radon",
    "radon.*",
]
ignore_missing_imports = true
```

### Common mypy Patterns

**structlog.get_logger() returns Any:**

```python
import structlog

def _get_logger() -> structlog.BoundLogger:
    return structlog.get_logger(__name__)  # type: ignore[no-any-return]
```

**asyncio.gather with return_exceptions:**

```python
import asyncio

async def run_parallel() -> list[dict]:
    results = await asyncio.gather(
        task_a(), task_b(), task_c(),
        return_exceptions=True,
    )
    cleaned = []
    for result in results:
        if isinstance(result, Exception):
            continue
        cleaned.append(result)  # type: ignore[assignment]
    return cleaned
```

**Pydantic models and TYPE_CHECKING:**

```python
# BAD - forward ref breaks at runtime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from tapps_mcp.scoring.models import ScoreResult

class Response(BaseModel):
    result: ScoreResult  # Pydantic cannot resolve this

# GOOD - import at runtime with noqa
from tapps_mcp.scoring.models import ScoreResult  # noqa: TC001

class Response(BaseModel):
    result: ScoreResult
```

**BaseSettings constructor with dict spread:**

```python
from pydantic_settings import BaseSettings

class ScoringWeights(BaseSettings):
    complexity: float = 0.2
    security: float = 0.3

# BaseSettings accepts many params beyond model fields
weights = ScoringWeights(**config_dict)  # type: ignore[arg-type]
```

### mypy Override Patterns

When `ignore_missing_imports = true` is set for optional dependencies,
do not add redundant `# type: ignore[import-untyped]` comments. mypy
will not flag those imports, and the comments become "unused-ignore" errors.

```python
# When pyproject.toml has ignore_missing_imports for faiss:
import faiss  # No type: ignore needed

# WRONG - this becomes an "unused type: ignore" error
import faiss  # type: ignore[import-untyped]
```

## Bandit (v1.9+ Security Scanning)

### Configuration

```toml
# pyproject.toml
[tool.bandit]
exclude_dirs = ["tests", "docs"]
skips = ["B101"]  # skip assert warnings (used in tests)
```

### Key Security Rules

| Rule | Description | Severity |
|---|---|---|
| B101 | Use of assert in non-test code | Low |
| B102 | exec() usage | High |
| B301 | Pickle usage (deserialization risk) | Medium |
| B602 | subprocess with shell=True | High |
| B608 | SQL injection via string formatting | High |
| B614 | AI/ML model loading | Medium |
| B615 | AI/ML prompt injection | Medium |

### Running Bandit

```bash
# Scan all source files
bandit -r src/ -f json

# Scan with confidence filter
bandit -r src/ --confidence-level medium

# Skip specific rules
bandit -r src/ --skip B101,B301
```

### Bandit in TappsMCP Pipeline

TappsMCP's `tapps_security_scan` tool runs bandit and secret detection:

```python
async def security_scan(file_path: str) -> dict:
    """Run bandit + secret detection on a Python file."""
    bandit_result = await run_bandit(file_path)
    secret_result = scan_for_secrets(file_path)
    return {
        "bandit_issues": bandit_result.issues,
        "secrets_found": secret_result.findings,
        "severity_counts": bandit_result.severity_counts,
    }
```

## Radon (v6.0+ Complexity Metrics)

### Metrics Provided

| Metric | Description | Good Threshold |
|---|---|---|
| Cyclomatic Complexity (CC) | Number of independent paths | CC < 10 per function |
| Maintainability Index (MI) | Overall maintainability score | MI > 20 |
| Halstead Metrics | Operator/operand complexity | Varies |
| Raw Metrics | LOC, LLOC, SLOC, comments | Varies |

### Running Radon

```bash
# Cyclomatic complexity
radon cc src/ -a -nc

# Maintainability index
radon mi src/ -s

# Raw metrics
radon raw src/ -s
```

### Interpreting Complexity Grades

| Grade | CC Range | Interpretation |
|---|---|---|
| A | 1-5 | Simple, low risk |
| B | 6-10 | Moderate, manageable |
| C | 11-15 | Complex, needs attention |
| D | 16-20 | High complexity, refactor |
| E | 21-30 | Very high, significant risk |
| F | 31+ | Untestable, must refactor |

### Direct Mode (Library Usage)

When radon is installed as a library, use it directly instead of subprocess:

```python
from radon.complexity import cc_visit
from radon.metrics import mi_visit

def analyze_complexity(source: str) -> dict:
    """Analyze complexity using radon as a library."""
    cc_results = cc_visit(source)
    mi_score = mi_visit(source, multi=True)

    return {
        "functions": [
            {
                "name": r.name,
                "complexity": r.complexity,
                "grade": chr(ord("A") + min(r.complexity // 5, 5)),
            }
            for r in cc_results
        ],
        "maintainability_index": mi_score,
    }
```

## Vulture (Dead Code Detection)

### What Vulture Detects

- Unused functions and methods
- Unused classes
- Unused imports
- Unused variables
- Unreachable code after return/raise

### Configuration

```toml
# pyproject.toml
[tool.vulture]
min_confidence = 80
paths = ["src/"]
exclude = ["tests/", "docs/"]
```

### Running Vulture

```bash
# Basic scan
vulture src/ --min-confidence 80

# With whitelist for known false positives
vulture src/ whitelist.py --min-confidence 80
```

### Whitelist Pattern

Create a whitelist file for intentional "unused" code:

```python
# whitelist.py
# These are used by the MCP framework via decoration
tapps_score_file  # noqa
tapps_quick_check  # noqa
tapps_init  # noqa
```

### TappsMCP Dead Code Tool

```python
async def scan_dead_code(file_path: str, min_confidence: int = 80) -> dict:
    """Scan a Python file for dead code using vulture."""
    result = await run_vulture(file_path, min_confidence)
    return {
        "dead_code": [
            {
                "name": item.name,
                "type": item.typ,
                "line": item.first_lineno,
                "confidence": item.confidence,
            }
            for item in result.items
        ],
        "total_items": len(result.items),
    }
```

## Pre-Commit Integration

### Comprehensive Hook Configuration

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.19.0
    hooks:
      - id: mypy
        args: [--strict]
        additional_dependencies:
          - pydantic>=2.0
          - structlog

  - repo: https://github.com/PyCQA/bandit
    rev: "1.9.0"
    hooks:
      - id: bandit
        args: [-r, --skip, "B101"]

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-yaml
      - id: check-toml
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-added-large-files
        args: [--maxkb=500]
```

### CI Pre-Commit Validation

```yaml
# .github/workflows/pre-commit.yml
name: Pre-commit
on: [pull_request]
jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: pre-commit/action@v3.0.1
```

## pip-audit (Dependency Vulnerability Scanning)

### Basic Usage

```bash
# Scan installed packages
pip-audit

# Scan from requirements file
pip-audit -r requirements.txt

# JSON output for CI
pip-audit --format json --output audit.json
```

### Configuration

```toml
# pyproject.toml (via pip-audit config)
[tool.pip-audit]
vulnerability-service = "osv"
```

### CI Integration

```yaml
steps:
  - name: Audit dependencies
    run: pip-audit --strict --desc
```

## Tool Orchestration in TappsMCP

### Parallel Execution

TappsMCP runs tools concurrently for full scoring:

```python
import asyncio

async def full_score(file_path: str) -> dict:
    """Run all quality tools in parallel."""
    ruff_task = asyncio.create_task(run_ruff(file_path))
    mypy_task = asyncio.create_task(run_mypy(file_path))
    bandit_task = asyncio.create_task(run_bandit(file_path))
    radon_task = asyncio.create_task(run_radon(file_path))

    results = await asyncio.gather(
        ruff_task, mypy_task, bandit_task, radon_task,
        return_exceptions=True,
    )

    return combine_scores(results)
```

### Quick vs Full Scoring

| Mode | Tools Used | Time | Accuracy |
|---|---|---|---|
| Quick | ruff only + AST heuristic | < 500ms | Good |
| Full | ruff + mypy + bandit + radon | 2-10s | Best |

### Tool Detection and Fallback

```python
from tapps_mcp.tools.tool_detection import detect_installed_tools

def get_available_scorers() -> list[str]:
    """Detect which quality tools are installed."""
    tools = detect_installed_tools()
    available = ["ruff"]  # always available (bundled)

    if tools.mypy:
        available.append("mypy")
    if tools.bandit:
        available.append("bandit")
    if tools.radon:
        available.append("radon")

    return available
```

## Scoring Categories

TappsMCP scores across seven categories using tool results:

| Category | Primary Tool | Weight |
|---|---|---|
| Complexity | radon (CC, MI) | 15% |
| Security | bandit + secrets | 20% |
| Maintainability | radon MI + ruff | 15% |
| Test Coverage | coverage.py | 10% |
| Performance | ruff + AST | 10% |
| Structure | ruff + AST | 15% |
| Developer Experience | ruff formatting | 15% |

## Quality Gate Presets

```python
QUALITY_PRESETS = {
    "standard": {"min_score": 70, "description": "General projects"},
    "strict": {"min_score": 80, "description": "Production code"},
    "framework": {"min_score": 75, "description": "Library/framework code"},
}
```

## Anti-Patterns

### Ignoring All Warnings

Never disable entire rule categories without justification:

```toml
# BAD
ignore = ["E", "W", "F"]

# GOOD - ignore specific rules with documented reasons
ignore = [
    "PLR0913",  # dispatch functions inherently have many params
]
```

### Inconsistent Tool Versions

Pin tool versions in CI and pre-commit to avoid surprise failures:

```yaml
# BAD
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: main  # floating reference

# GOOD
- repo: https://github.com/astral-sh/ruff-pre-commit
  rev: v0.15.0  # pinned version
```

### Running Tools Sequentially

Always run independent tools in parallel. Sequential execution wastes
CI time and developer patience.

## Quick Reference

| Tool | Purpose | Speed | Config File |
|---|---|---|---|
| ruff | Lint + format | Very fast | pyproject.toml |
| mypy | Type checking | Moderate | pyproject.toml |
| bandit | Security scan | Fast | pyproject.toml |
| radon | Complexity | Fast | N/A |
| vulture | Dead code | Fast | pyproject.toml |
| pip-audit | Dependency CVEs | Moderate | N/A |
| pre-commit | Git hook runner | Varies | .pre-commit-config.yaml |
