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

Once installed **and loaded**, the TappsMCP tools are available in every
session. Use `/tapps-finish-task` before declaring work complete,
`/tapps-review-pipeline` for multi-file review, and direct MCP tools
(`tapps_quick_check`, `tapps_validate_changed`) during edit loops.

**Known issues, re-verified against this bundle on 2026-09-16:**

- **Fixed:** the plugin used to fail to load. `claude plugin install
  tapps-mcp` exited `0`, but `claude plugin list` then showed
  `tapps-mcp@tapps-mcp` as `✘ failed to load` with
  `Error: Dependency "docs-mcp@tapps-mcp" is not installed` — `plugin.json`
  declared a `docs-mcp` dependency this marketplace never lists. That
  dependency is removed; a clean install now loads without error.
- **Still open — the tools above are not all actually reachable yet.**
  This bundle's `.mcp.json` registers one server (name `tapps-mcp`), and a
  plugin-registered server's tools surface under
  `mcp__plugin_tapps-mcp_tapps-mcp__*` (confirmed by installing a throwaway
  plugin and watching a tool execute — a plugin-registered server is
  namespaced `mcp__plugin_<plugin>_<server>__`, not a bare `mcp__<server>__`).
  Counted directly from this bundle's `skills/` and `agents/`, none of the
  shipped tool references use that prefix: 103 call `mcp__nlt-build__*`, 29
  call `mcp__nlt-linear-issues__*`, 8 call `mcp__nlt-setup__*`, 6 call
  `mcp__nlt-release-ship__*`, and 3 call `mcp__nlt-memory__*` — the
  pre-plugin, direct-MCP server names, none of which this bundle registers.
  A further 7 references already read `mcp__tapps-mcp__*`, which is closer
  but still not the working prefix. `/tapps-finish-task` in particular calls
  `mcp__nlt-build__tapps_checklist`, `mcp__nlt-build__tapps_validate_changed`,
  and `mcp__nlt-build__tapps_lookup_docs` — none of which resolve after a
  clean install. Rewriting these prefixes is tracked as a separate fix.
  **Use `tapps-mcp init` in the main repo README for a working setup
  today** — the plugin now installs and loads cleanly, but its documented
  primary workflow is not yet reachable through it.

## License

MIT — see `LICENSE`.
