# Changelog

## [3.12.90] — 2026-09-16

### Fixed

- `.mcp.json` is now tracked (was silently dropped by the repo's `.mcp.json`
  gitignore pattern) — every shipped skill/agent/hook that calls an
  `mcp__tapps-mcp__*` tool now has a declared MCP server to resolve against.
- `plugin.json`'s `author`/`dependencies`/`userConfig` shapes corrected
  against `claude plugin validate` (object author, array dependencies,
  `title` instead of `label`, no `enum`/`options`/`select` key).
- `homepage`/`repository` URLs corrected from a placeholder
  `github.com/tapps-mcp/tapps-mcp` to the real
  `github.com/wtthornton/TappsMCP`.
- README corrected to list all 5 shipped agents (was naming 3) and to give
  a working install path via a local marketplace add.

### Added

- `LICENSE` and this `CHANGELOG.md` (previously unshipped).
- `.claude-plugin/marketplace.json`, hand-maintained like
  `plugin/cursor/marketplace.json`.

## [3.12.x] — earlier

- `build-plugin` (`PluginBuilder`) unified to delegate to
  `generate_claude_plugin_bundle()` — one implementation now serves both
  entry points, in place of a second, drifted, never-installed
  implementation.
