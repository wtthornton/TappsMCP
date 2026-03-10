# TappsMCP Quality Standards for BugBot

This project uses TappsMCP (Code Quality MCP Server) for automated quality
analysis. The following standards are enforced during PR review.

## Code Quality Standards

All Python files must meet TappsMCP scoring thresholds:
- Overall score: >= 70 (development), >= 80 (staging), >= 90 (production)
- No individual category score below 50
- Security floor: 50/100 (files with critical security issues always fail)

### Scoring Categories (aligned with TappsMCP 7-category model)

| Category | Weight | What BugBot Should Check |
|----------|--------|-------------------------|
| **Complexity** | 0.18 | Cyclomatic complexity > 10, deeply nested functions (> 4 levels) |
| **Security** | 0.27 | Hardcoded secrets, unsafe deserialization, injection vulns, eval/exec |
| **Maintainability** | 0.24 | Functions > 50 lines, poor naming, missing type annotations |
| **Test Coverage** | 0.13 | Functions without test coverage, real external service calls in tests |
| **Performance** | 0.08 | Nested loops on large data, sync I/O in async context, N+1 queries |
| **Structure** | 0.05 | Missing pyproject.toml, tests/, README, inconsistent project layout |
| **DevEx** | 0.05 | Missing docstrings on public API, no AGENTS.md, no CI config |

### Severity Mapping

| Severity | Action | Examples |
|----------|--------|----------|
| **Critical** (P0) | Block merge | Hardcoded secrets, SQL injection, eval() on user input, security score < 50 |
| **Warning** (P1) | Flag for review | Complexity > 10, missing type hints, functions > 50 lines |
| **Info** (P2) | Suggestion only | Missing docstrings, style inconsistencies, minor dead code |

## Security Requirements

Flag any of the following as **blocking** (P0) issues:
- Hardcoded passwords, API keys, tokens, or secrets
- Use of `eval()` or `exec()` with non-literal arguments
- `pickle.loads()` on data from external sources
- Raw SQL string concatenation (use parameterized queries)
- File path operations without validation against allowed base dir
- `subprocess` calls with `shell=True` and interpolated user input

## Dependency Vulnerabilities

Flag as **blocking** (P0):
- Known CVEs in direct dependencies (check with `tapps_dependency_scan`)
- Unpinned dependencies in production requirements

## Python Style Rules

Flag the following as **warnings** (P1):
- Public functions and methods without type annotations
- Public classes and functions without docstrings
- Bare `except:` clauses (must specify exception type)
- Functions with cyclomatic complexity > 10
- Functions longer than 50 lines (excluding docstrings/blanks)
- Mutable default arguments in function signatures

## Testing Requirements

Flag the following as **warnings** (P1):
- New public functions without a corresponding test in `tests/`
- Tests that make real HTTP requests without mocking
- Tests that read from or write to production configuration files
- Tests that depend on environment variables without explicit fixtures

## Directory Hierarchy

This `BUGBOT.md` applies to all files in `.cursor/` and subdirectories.
Place a subdirectory `BUGBOT.md` to override these rules for specific
sub-packages with different thresholds.
