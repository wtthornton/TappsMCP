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
- **Skills** (25): `/tapps-finish-task`, `/tapps-review-pipeline`,
  `/linear-read`, and 22 more — see `skills/`. (`linear-issue` ships via
  `tapps-mcp init`/`upgrade` but not in this plugin bundle — see below.)
- **Hooks**: Session start, post-edit reminders, stop gate, and more —
  see `hooks/hooks.json`

## Usage

Once installed **and loaded**, the TappsMCP tools are available in every
session. Use `/tapps-finish-task` before declaring work complete,
`/tapps-review-pipeline` for multi-file review, and direct MCP tools
(`tapps_quick_check`, `tapps_validate_changed`) during edit loops.

**Known issues, re-verified against this bundle on 2026-09-17:**

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
- **`linear-issue` excluded from this bundle (TAP-7753 round 2):** every
  write it performs — epic/story creation, lint, triage — is gated behind
  `mcp__nlt-linear-issues__docs_*` tools that live only on the separate
  `docs-mcp` server (TAP-7758: this bundle does not ship or depend on it).
  Named rather than counted, because three hand-typed counts of this set
  disagreed: `docs_generate_epic`, `docs_generate_story`,
  `docs_linear_triage`, `docs_lint_linear_issue`, `docs_save_linear_issue`
  and `docs_validate_linear_issue`. Unlike the three skills below there is no
  reduced mode — the whole skill is one docs-mcp-centered chain — so it is
  filtered out at build time rather than shipped non-functional, and remains
  fully available (docs-mcp genuinely present) via `tapps-mcp init`/`upgrade`.
- **Three skills degrade gracefully instead, and say so in their own
  `SKILL.md` under a `## Degrades without` heading:**
  - `linear-read` — carries **zero** docs-mcp references. Its only gap is
    `mcp__plugin_linear_linear__` (`list_issues`/`get_issue`), which
    belongs to a separate, independently installed Linear plugin this
    bundle does not register (TAP-7771: declaring it a `plugin.json`
    dependency would recreate the exact unsatisfiable-dependency failure
    fixed above the moment an operator hasn't also added that plugin's
    marketplace). Without it, only the cache-first snapshot mechanics still
    work; live Linear reads do not.
  - `linear-release-update` — the same `mcp__plugin_linear_linear__` gap
    (`save_document`), plus `mcp__nlt-release-ship__docs_release_gate`
    (docs-mcp, same TAP-7758 gap as `linear-issue`, but here the skill still
    has a real fallback: `tapps_release_update(dry_run=true)` previews the
    release body using only bundled tools).
  - `tapps-continue-session` — the same `mcp__plugin_linear_linear__` gap
    (`get_issue`, the `TAP-####` re-verification step). Without it, handoff
    rehydration, sha/PR ground-truth checks, and the continue block itself
    are all unaffected — only the live Linear-id lookup is skipped.
  `scripts/validate-claude-plugin.sh` requires each of these references to
  be documented in the SAME file it appears in — a doc note in one skill
  never exempts an undocumented reference anywhere else.

## License

MIT — see `LICENSE`.
