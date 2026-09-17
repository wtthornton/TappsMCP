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
- **Fixed (TAP-7753):** most shipped tool references now resolve. A
  plugin-registered server's tools surface under
  `mcp__plugin_tapps-mcp_tapps-mcp__*`, not a bare `mcp__<server>__`
  (confirmed by installing a throwaway plugin and watching a tool
  execute). Every skill/agent/hook reference that named one of this
  bundle's own tools under a pre-plugin prefix — `mcp__nlt-build__`,
  `mcp__nlt-setup__`, `mcp__nlt-memory__`, `mcp__tapps-mcp__`, and the
  `mcp__tapps_mcp__` / `mcp__tapps-quality__` legacy aliases — is now
  rewritten to that prefix at build time, gated per tool name against
  this bundle's own live tool list (`tapps-mcp serve`'s registered
  `ALL_TOOL_NAMES`) so a rewrite can never point at a tool the server
  does not actually expose.
- **Still open — two gaps this fix deliberately did not paper over:**
  1. `mcp__nlt-linear-issues__docs_*` (in `linear-issue`, `linear-read`)
     and `mcp__nlt-release-ship__docs_*` (in `linear-release-update`) name
     tools — `docs_generate_epic`, `docs_validate_linear_issue`,
     `docs_release_gate`, and others — that live only on the separate
     `docs-mcp` server. This bundle does not ship or depend on that server
     (the dependency was removed in TAP-7758 for being unsatisfiable), so
     no prefix rewrite can make these resolve; they are a real capability
     gap, not a namespace bug.
  2. `mcp__plugin_linear_linear__*` (in `linear-issue`, `linear-read`,
     `linear-release-update`) belongs to a separate, independently
     installed Linear plugin this bundle does not register. Declaring it
     as a `plugin.json` dependency would recreate the exact
     unsatisfiable-dependency failure fixed above the moment an operator
     hasn't also added that plugin's marketplace — and is rejected outright
     by this bundle's own dependency-resolvability check (TAP-7771).
     Stripping the references would gut those three skills' actual
     purpose (they exist to wrap Linear's generator/validator flow).
  `scripts/validate-claude-plugin.sh` names both gaps explicitly on every
  run rather than passing around them.

## License

MIT — see `LICENSE`.
