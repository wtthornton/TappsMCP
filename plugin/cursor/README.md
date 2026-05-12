# TappsMCP Quality Tools for Cursor

Code quality scoring, security scanning, and quality gates for Python projects.

## Installation

**Via Cursor Marketplace:**
Search for "TappsMCP" at [cursor.com/marketplace](https://cursor.com/marketplace)

**Via deep link:**
```
cursor://install-plugin/tapps-mcp-plugin
```

**In Cursor:**
Run `/add-plugin tapps-mcp-plugin` in the command palette.

## Requirements

- Python 3.12+
- `uv` or `uvx` installed (`pip install uv`)
- Cursor 2.5 or later

## Quick Start

1. After installation, open a Python project
2. The TappsMCP MCP server starts automatically
3. Ask Cursor: "Check the quality of this file" — TappsMCP will score it

## What's Included

- **3 Skills**: `tapps-score`, `tapps-gate`, `tapps-validate`
- **3 Agents**: `tapps-reviewer`, `tapps-researcher`, `tapps-validator`
- **3 Rules**: pipeline (always), python-quality (auto-attach), expert-consultation (agent-requested)
- **Hooks**: `afterFileEdit` auto-quality-check, `stop` validation gate, `beforeMCPExecution` logging

## Quality Scoring Categories

TappsMCP scores Python code across 7 categories (0-100 each):

| Category | What It Checks |
|----------|---------------|
| Correctness | Logic errors, type safety, edge cases |
| Security | Vulnerabilities, injection risks, secrets |
| Maintainability | Complexity, naming, structure |
| Performance | Efficiency, resource usage, scaling |
| Documentation | Docstrings, comments, clarity |
| Testing | Coverage, edge cases, assertions |
| Style | PEP 8, formatting, consistency |

## License

MIT
