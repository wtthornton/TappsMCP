# TappsMCP Quality Tools for Cursor

Code quality scoring, security scanning, and quality gates for Python projects.

## Installation

**Via Cursor Marketplace:** search for "TappsMCP" at [cursor.com/marketplace](https://cursor.com/marketplace)

**Via deep link:** `cursor://install-plugin/tapps-mcp-plugin`

**In Cursor:** run `/add-plugin tapps-mcp-plugin` in the command palette.

## Requirements

- Python 3.12+
- `uv` or `uvx` installed
- Cursor 2.5 or later

## What's Included

- **MCP Server**: `tapps-mcp serve` with 42+ quality tools (via `uvx`)
- **Agents**: tapps-reviewer, tapps-researcher, tapps-validator, tapps-docs-reviewer, tapps-docs-validator
- **Skills**: finish-task, refactor, review-pipeline, docs-refresh/bootstrap/finish-task, linear-issue/read, memory, and more
- **Hooks**: before MCP logging, after-edit quality reminders, stop validation gate
- **Rules**: pipeline (always), Python quality (auto-attach), expert consultation (agent-requested)

## Usage

Once installed, TappsMCP tools are available in every session:

- `@tapps-finish-task` before declaring work complete
- `@tapps-refactor` before changing a function signature or deleting a symbol
- `@tapps-review-pipeline` for multi-file review
- `@tapps-docs-refresh` / `@tapps-docs-bootstrap` for documentation workflows
- Direct MCP tools (`tapps_quick_check`, `tapps_validate_changed`) during edit loops

## License

MIT
