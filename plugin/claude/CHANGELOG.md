# Changelog

## [Unreleased]

### Fixed

- **Tool references now resolve (TAP-7753).** A plugin-registered MCP
  server's tools are namespaced `mcp__plugin_<pluginName>_<serverKey>__`,
  never a bare `mcp__<serverKey>__` — confirmed empirically by installing
  two throwaway plugins and observing an executed tool's real namespace.
  This bundle's plugin name and its single `.mcp.json` server key are both
  `tapps-mcp`, so the working prefix is `mcp__plugin_tapps-mcp_tapps-mcp__`.
  Every shipped skill/agent/hook reference that named one of this bundle's
  own tools under a pre-plugin prefix (`mcp__nlt-build__`, `mcp__nlt-setup__`,
  `mcp__nlt-memory__`, `mcp__tapps-mcp__`, and the `mcp__tapps_mcp__` /
  `mcp__tapps-quality__` legacy aliases) is rewritten to that prefix at
  build time, gated per tool name against this bundle's own live tool list
  so a rewrite can never point at a tool the server does not actually
  expose. The previous `[3.12.90]` entry below claiming tools "now [have] a
  declared MCP server to resolve against" was **only half true**: a
  registered server is necessary but was not sufficient — the reference
  prefix itself was still wrong until this fix.
- **Two known gaps remain, deliberately not silently patched over:**
  `mcp__nlt-linear-issues__docs_*` and `mcp__nlt-release-ship__docs_*`
  references (in `linear-issue`, `linear-read`, `linear-release-update`)
  name tools that live only on the separate `docs-mcp` server, which this
  bundle does not ship or depend on (that dependency was removed in
  TAP-7758 for being unsatisfiable). `mcp__plugin_linear_linear__`
  references belong to a separate, independently-installed Linear plugin
  this bundle does not register; declaring it as a `plugin.json`
  dependency would recreate the exact unsatisfiable-dependency failure
  TAP-7758 just fixed (and is rejected outright by this bundle's own
  dependency-resolvability check per TAP-7771), while stripping the
  references would gut those three skills' actual purpose. Tracked open,
  not resolved by this fix.

## [3.12.90] — 2026-09-16

### Fixed

- `.mcp.json` is now tracked (was silently dropped by the repo's `.mcp.json`
  gitignore pattern), so this bundle declares an MCP server for its tools to
  resolve against — necessary but not sufficient on its own; see TAP-7753
  above for the reference-prefix half of this fix.
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
