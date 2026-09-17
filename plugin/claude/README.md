# TappsMCP - Claude Code Plugin

Code quality scoring, security scanning, and quality gates
for Python projects.

## Installation

This marketplace's `.claude-plugin/marketplace.json` lives under
`plugin/claude/` in the `wtthornton/TappsMCP` repo, not at the repo root, so
the bare `owner/repo` marketplace shorthand will not find it. Add it from a
local checkout instead:

```
git clone https://github.com/wtthornton/TappsMCP.git
claude plugin marketplace add /path/to/TappsMCP/plugin/claude
claude plugin install tapps-mcp
```

## What's Included

- **MCP Server**: `tapps-mcp serve` (`uvx tapps-mcp serve`), 12+ quality
  tools (scoring, security scanning, quality gates, docs lookup, and more)
- **Agents** (5): tapps-reviewer, tapps-researcher, tapps-validator,
  tapps-review-fixer, tapps-frontend-reviewer
- **Skills** (26): `/tapps-finish-task`, `/tapps-review-pipeline`,
  `/linear-read`, and 23 more — see `skills/`
- **Hooks**: Session start, post-edit reminders, stop gate, and more —
  see `hooks/hooks.json`

## Usage

Once installed, the TappsMCP tools are available in every
session. Use `/tapps-finish-task` before declaring work complete,
`/tapps-review-pipeline` for multi-file review, and direct MCP tools
(`tapps_quick_check`, `tapps_validate_changed`) during edit loops.

## License

MIT — see `LICENSE`.
