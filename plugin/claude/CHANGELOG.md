# Changelog

## [Unreleased]

### Fixed

- **The graceful-degradation exemption is cross-plugin only, and the bundle no
  longer routes to a skill it does not ship (TAP-7753 round 3).** Round 2's
  exemption (below) was gated on nothing but "this string appears under a
  `## Degrades without` heading in this file", so a bare
  `mcp__tapps-mcp__tapps_quick_check` — the pre-plugin spelling this check
  exists to reject — passed simply by documenting itself.
  `scripts/validate-claude-plugin.sh` now exempts only a
  `mcp__plugin_<other-plugin>_<server>__` prefix, documented in the same file,
  under a heading that is not inside a code fence, in a section that ends at
  the next heading of any depth, and only in a file under `skills/`. Eleven
  controls in `scripts/test-validate-claude-plugin-prefix-resolvability.sh` —
  now actually invoked by CI — hold those clauses; the five new ones were each
  verified to go red against the round-2 validator.
  Separately, filtering `linear-issue` out of the bundle left six shipped
  references still routing to it (including a mandatory "Linear writes only via
  `linear-issue`"); every skill naming an unshipped skill now carries a
  bundle-scoped availability note, emitted at build time and derived from the
  exclusion set, so a future exclusion is annotated automatically.
  **Known-open:** tightening the exemption exposed one genuine reference this
  bundle cannot resolve — `mcp__nlt-release-ship__docs_release_gate`, used by
  `linear-release-update` step 1b. It belongs to `docs-mcp`, not to another
  plugin, so no amount of documentation makes it resolvable here; how that
  skill should ship is an open decision and the validator fails on it
  deliberately rather than exempting it.
- **`linear-issue` excluded from this bundle; three sibling skills documented
  as gracefully degrading instead (TAP-7753 round 2).** The `[3.12.90]`
  entry below said `mcp__nlt-linear-issues__docs_*` gaps lived "in
  `linear-issue`, `linear-read`" — that was wrong for `linear-read`, which
  carries **zero** `docs-mcp` references (verified by scanning its shipped
  `SKILL.md`); only `linear-issue` ever cited `docs-mcp` tools. `linear-issue`
  is unusable in this bundle regardless — every write it performs (lint,
  validate, save) is gated behind a `docs-mcp` tool with no fallback — so it
  is now filtered out of the Claude plugin bundle at build time (a
  bundle-writer filter, not a removal from the underlying skill registry;
  it still ships in full via `tapps-mcp init`/`upgrade`, where `docs-mcp`
  genuinely exists). `linear-read`, `linear-release-update`, and
  `tapps-continue-session` remain shipped: each now carries its own
  `## Degrades without` section naming exactly which `mcp__plugin_linear_linear__`
  (or, for `linear-release-update`, `mcp__nlt-release-ship__docs_release_gate`)
  reference it cannot resolve in this bundle and what still works without it.
  `scripts/validate-claude-plugin.sh`'s prefix-resolvability check now
  accepts such a reference only when that same file documents it — an
  undocumented cross-plugin reference anywhere else still fails the check.
  *(Amended by the round-3 entry above: documenting a reference is necessary
  but no longer sufficient. `mcp__nlt-release-ship__docs_release_gate` is not
  a cross-plugin prefix and is no longer accepted on documentation alone.)*
- **Two dead tool grants removed from `linear-release-update`.**
  `mcp__nlt-release-ship__docs_generate_release_update` and
  `mcp__nlt-release-ship__docs_validate_release_update` were declared in
  `allowed-tools` but never invoked anywhere in the skill body (the body
  calls `docs_release_gate`, not either of these) — dead grants, removed.

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
- **Two known gaps remain, deliberately not silently patched over.**
  *(Superseded by the TAP-7753 round 2 entry above — the `linear-issue`,
  `linear-read` attribution below was wrong for `linear-read`, which has
  zero `docs-mcp` references; `linear-issue` is no longer shipped in this
  bundle at all. Left here for the historical record of what round 1 knew
  at the time.)*
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
