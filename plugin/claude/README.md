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

Once installed and loaded, the TappsMCP tools are available in every
session. Use `/tapps-finish-task` before declaring work complete,
`/tapps-review-pipeline` for multi-file review, and direct MCP tools
(`tapps_quick_check`, `tapps_validate_changed`) during edit loops.

**Known issue (verified 2026-09-16): install currently succeeds but the
plugin fails to load.** `claude plugin install tapps-mcp` exits `0`, but
`claude plugin list` then shows `tapps-mcp@tapps-mcp` as `✘ failed to load`
with `Error: Dependency "docs-mcp@tapps-mcp" is not installed`. This
manifest (`plugin.json` declares a `docs-mcp` dependency that this
marketplace does not list) needs a fix tracked separately — the tools above
are not actually reachable until then. Use `tapps-mcp init` in the main repo
README for a working setup today.

## License

MIT — see `LICENSE`.
