# TappsMCP Reviewer Agent Memory

## MCP Tool Availability
- `mcp__tapps-mcp__tapps_quick_check` and related tools are NOT available when Claude Code
  runs as the tapps-reviewer sub-agent (the MCP server is the tool being reviewed, not the host).
- Fallback: perform manual static review using project conventions from CLAUDE.md and the 7
  scoring categories (correctness, security, maintainability, performance, documentation,
  testing, style).

## Scoring Rubric (7 Categories, 0-100 each)
1. Correctness - logic errors, type safety, edge cases
2. Security - vulnerabilities, injection risks, secrets
3. Maintainability - complexity, naming, structure (PLR0913/PLR0912 suppressed globally)
4. Performance - efficiency, resource usage, scaling
5. Documentation - docstrings, comments, clarity
6. Testing - coverage, edge cases, assertions
7. Style - PEP 8, formatting, ruff compliance, line length <= 100

## Key Project Conventions (from CLAUDE.md)
- `from __future__ import annotations` at top of every file
- `pathlib.Path` for all file paths; `Path` in TYPE_CHECKING if only used in annotations
- Type annotations everywhere — mypy --strict must pass
- structlog for logging (never print() or logging directly)
- Pydantic v2 for config and data structures
- Ruff line length: 100
- Async/await for tool handlers and external I/O
- All file ops go through security/path_validator.py (server tools only; generators bypass by design)

## Known Issues Seen
- platform_generators.py: Path imported under TYPE_CHECKING only — correct since annotations
  use `from __future__ import annotations`. Direct Path usage in function bodies would need
  runtime import, but all Path params are received as arguments, not constructed.
- doctor.py: Uses `import sys as _sys` inside function body (lazy import pattern) — acceptable
  but slightly inconsistent with top-level import style.
- platform_generators.py: `generate_claude_plugin_bundle` has a hardcoded version default
  `"0.3.0"` that does not track the installed TappsMCP version — potential drift issue.
- platform_generators.py: `generate_agent_teams_hooks` always marks bash scripts executable
  (no Windows branch) — could silently fail on Windows if called directly.
