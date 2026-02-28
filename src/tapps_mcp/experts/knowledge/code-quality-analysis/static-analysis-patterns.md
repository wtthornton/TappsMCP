# Static Analysis Patterns

## Overview

Static analysis tools examine code without executing it, identifying potential bugs,
security vulnerabilities, and code quality issues early in the development cycle.
This guide covers analysis categories, Python-specific tooling, configuration
strategies, and integration patterns.

## Common Static Analysis Categories

### Code Smells

- Long methods (excessive lines of code)
- Large classes (too many responsibilities)
- Duplicate code (DRY violations)
- Complex conditionals (high cyclomatic complexity)
- God objects (classes that know/do too much)
- Deep nesting (more than 3 levels)
- Feature envy (method uses another class more than its own)

### Security Vulnerabilities

- SQL injection risks (string formatting in queries)
- Cross-site scripting (XSS) vulnerabilities
- Insecure deserialization (pickle, yaml.load)
- Hardcoded credentials (API keys, passwords in source)
- Weak cryptographic algorithms (MD5, SHA1 for security)
- Command injection (subprocess with shell=True)
- Path traversal (unsanitized file paths)

### Performance Issues

- Inefficient algorithms (O(n^2) when O(n) possible)
- Unnecessary object creation in loops
- Memory leaks (unclosed resources)
- Database N+1 queries
- Inefficient string concatenation (use join instead)
- Redundant computations (cache results)

### Code Style and Best Practices

- Naming convention violations
- Missing type annotations
- Unused imports and variables
- Inconsistent formatting
- Deprecated API usage
- Missing error handling at system boundaries

## Python Static Analysis Tools

### Ruff - Unified Linter and Formatter

Ruff (v0.15+) is the recommended single-tool solution for Python linting and
formatting, replacing flake8, isort, pyflakes, and more:

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = [
    "E", "W", "F", "I", "N", "UP", "B",
    "A", "C4", "SIM", "TCH", "RUF", "S",
    "ANN", "PT", "PL",
]
ignore = [
    "PLR0913",  # too-many-arguments
    "PLR0912",  # too-many-branches
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S101", "ANN"]
```

### Rule Selection Strategy

Adopt rules in tiers based on project maturity:

**Tier 1 - Always enable (catches real bugs):**

```toml
select = ["E", "F", "W", "B", "UP", "I"]
```

These catch syntax errors, undefined names, unused imports, common bugs,
and sort imports. Zero false positives in practice.

**Tier 2 - Enable for code quality:**

```toml
select = ["E", "F", "W", "B", "UP", "I", "N", "SIM", "C4", "RUF", "TCH"]
```

Adds naming conventions, simplification suggestions, comprehension
improvements, and ruff-specific rules.

**Tier 3 - Enable for strict projects:**

```toml
select = [
    "E", "F", "W", "B", "UP", "I", "N", "SIM", "C4", "RUF", "TCH",
    "ANN", "S", "PL", "PT",
]
```

Adds type annotation enforcement, security rules, pylint checks, and
pytest style rules.

### mypy - Static Type Checking

mypy (v1.19+) provides static type checking for Python:

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.12"
strict = true
warn_return_any = true
warn_unused_configs = true
show_error_codes = true
```

### mypy Override Patterns

Handle special cases with per-module overrides:

```toml
# Untyped decorators from external libraries
[[tool.mypy.overrides]]
module = "tapps_mcp.server"
disallow_untyped_decorators = false

# Optional dependencies that may not be installed
[[tool.mypy.overrides]]
module = ["mcp", "mcp.*", "faiss", "numpy"]
ignore_missing_imports = true
```

Key principle: when `ignore_missing_imports = true` is set, do NOT add
`# type: ignore[import-untyped]` comments - they become unused-ignore errors.

### Bandit - Security Scanner

Bandit (v1.9+) specializes in Python security analysis:

```toml
# pyproject.toml
[tool.bandit]
exclude_dirs = ["tests", "docs"]
skips = ["B101"]  # allow assert in production code if intentional
```

Key rules: B102 (exec), B301 (pickle), B602 (shell=True),
B608 (SQL injection), B614/B615 (AI/ML risks).

### Radon - Complexity Metrics

Radon (v6.0+) measures cyclomatic complexity and maintainability:

```bash
# Cyclomatic complexity with grades
radon cc src/ -a -nc

# Maintainability index
radon mi src/ -s
```

Complexity grades: A (1-5), B (6-10), C (11-15), D (16-20), E (21-30), F (31+).
Target: all functions at A or B grade (CC < 10).

## Integration Strategies

### Pre-Commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.19.0
    hooks:
      - id: mypy
        args: [--strict]
        additional_dependencies: [pydantic>=2.0]
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace
```

### CI/CD Integration

```yaml
# .github/workflows/quality.yml
name: Code Quality
on: [push, pull_request]

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install tools
        run: pip install ruff mypy bandit radon
      - name: Ruff lint
        run: ruff check src/ --output-format=github
      - name: Ruff format
        run: ruff format --check src/
      - name: Type check
        run: mypy --strict src/
      - name: Security scan
        run: bandit -r src/ --skip B101
      - name: Complexity check
        run: radon cc src/ -a -nc --total-average
```

### IDE Integration

All tools integrate with VS Code, PyCharm, and other editors:

```json
{
    "python.linting.enabled": true,
    "ruff.enable": true,
    "mypy.runUsingActiveInterpreter": true
}
```

## Parallel Tool Execution

### Running Tools Concurrently

For maximum speed, run independent tools in parallel:

```python
import asyncio

async def run_all_checks(file_path: str) -> dict:
    """Run all static analysis tools concurrently."""
    tasks = [
        asyncio.create_task(run_ruff_check(file_path)),
        asyncio.create_task(run_mypy_check(file_path)),
        asyncio.create_task(run_bandit_scan(file_path)),
        asyncio.create_task(run_radon_analysis(file_path)),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    return {
        "ruff": results[0] if not isinstance(results[0], Exception) else None,
        "mypy": results[1] if not isinstance(results[1], Exception) else None,
        "bandit": results[2] if not isinstance(results[2], Exception) else None,
        "radon": results[3] if not isinstance(results[3], Exception) else None,
    }
```

### Quick vs Full Analysis

| Mode | Tools | Time | Use Case |
|---|---|---|---|
| Quick | ruff + AST | < 500ms | Edit-lint-fix loops |
| Standard | ruff + mypy | 1-3s | Pre-commit hooks |
| Full | All tools | 5-15s | CI/CD, quality gates |

## AST-Based Fallback Analysis

When external tools are unavailable, use Python's AST for basic analysis:

```python
import ast

class ComplexityVisitor(ast.NodeVisitor):
    """Calculate cyclomatic complexity from AST."""

    def __init__(self) -> None:
        self.complexity = 1  # base complexity

    def visit_If(self, node: ast.If) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += len(node.values) - 1
        self.generic_visit(node)


def ast_complexity(source: str) -> int:
    """Calculate cyclomatic complexity using AST."""
    tree = ast.parse(source)
    visitor = ComplexityVisitor()
    visitor.visit(tree)
    return visitor.complexity
```

### Unused Import Detection via AST

```python
import ast

def find_unused_imports(source: str) -> list[str]:
    """Find imports not referenced in the code body."""
    tree = ast.parse(source)

    imported_names: set[str] = set()
    used_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name
                imported_names.add(name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                imported_names.add(name)
        elif isinstance(node, ast.Name):
            used_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                used_names.add(node.value.id)

    return sorted(imported_names - used_names)
```

## Best Practices

1. **Run early and often** - integrate into IDE and pre-commit hooks
2. **Fix immediately** - do not let technical debt accumulate
3. **Customize rules** - adjust to match your team's standards
4. **Track metrics** - monitor code quality trends over time
5. **Gradual adoption** - start with Tier 1 rules, expand as the team adapts
6. **Pin versions** - lock tool versions in CI to avoid surprise failures
7. **Automate fixes** - use `ruff --fix` for auto-fixable issues
8. **Parallel execution** - run independent tools concurrently

## Metrics to Track

| Metric | Tool | Target |
|---|---|---|
| Cyclomatic complexity | radon | CC < 10 per function |
| Maintainability index | radon | MI > 20 |
| Code duplication | ruff CPD | < 5% duplicate lines |
| Type coverage | mypy | 100% in strict mode |
| Security findings | bandit | 0 high severity |
| Dead code | vulture | 0 items at 80%+ confidence |
| Test coverage | coverage.py | > 80% line coverage |

## Anti-Patterns

### Suppressing All Warnings

```python
# BAD - blanket suppression hides real issues
# type: ignore
# noqa

# GOOD - specific suppression with justification
# type: ignore[no-any-return]  # structlog returns Any
# noqa: PLR0913  # dispatch function needs many params
```

### Inconsistent Configurations

Different developers or CI environments using different tool versions
or configurations causes confusion. Centralize in pyproject.toml.

### Ignoring Degraded Results

When a tool is missing and fallback analysis runs, the results are
less accurate. Track and report degraded status clearly.
