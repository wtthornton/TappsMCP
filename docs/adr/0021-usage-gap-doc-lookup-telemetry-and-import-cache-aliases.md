# 21. Usage-gap doc lookup: import/cache aliases + cross-channel telemetry

Date: 2026-06-16

## Status

accepted

## Context

`tapps_usage` / `usage-gaps-hint` can report `library_uses_without_lookup_docs`
after an agent already warmed docs via CLI `tapps-mcp lookup-docs` or when
`.tapps-mcp-cache/pyyaml/` exists but edited files `import yaml`.

Root causes (two independent channels):

1. **Telemetry channel** — `compute_gaps()` treats `tapps_lookup_docs` as satisfied
   only when the in-process MCP `CallTracker` or Stop-hook `loop-metrics.jsonl`
   records a lookup. CLI `lookup-docs` warms `.tapps-mcp-cache/` but does not
   update either substrate. SessionStart hooks intentionally use disk-only
   telemetry (`called_tools=set()`), so prior-session CLI lookups are invisible.

2. **Import vs cache key** — `find_uncached_libraries()` checks
   `cache.has(import_name)` literally. PyPI/import mismatches (`yaml` vs
   `pyyaml`, `cv2` vs `opencv-python`, `PIL` vs `pillow`) mark warmed docs as
   "uncached" and keep the gap open even when `used_lookup` is true.

Agents and handoff notes documented a workaround (one MCP `tapps_lookup_docs`
call after Reload Window). That clears CallTracker but does not fix the
underlying false positives or CLI parity.

## Decision

Implement a two-layer fix across **tapps-core** and **tapps-mcp**:

### Layer A — tapps-core: alias-aware cache resolution (import analyzer)

- Add `IMPORT_MODULE_ALIASES` for common import-name → cache-key mappings.
- Add `is_library_cached()` that checks, in order: direct `cache.has()`,
  alias candidates, `resolve_alias()`, then fuzzy match against known cache
  library dirs (threshold 0.85).
- Route `find_uncached_libraries()` through `is_library_cached()`.

**Effect:** `library_uses_without_lookup_docs` is suppressed when all external
imports in recent edits resolve to warmed cache entries, even without an MCP
lookup call.

### Layer B — tapps-mcp: cross-channel lookup telemetry

- Append successful lookups to `.tapps-mcp/.lookup-docs-events.jsonl`
  (rotates at 10 MB) from:
  - CLI `tapps-mcp lookup-docs`
  - MCP `tapps_lookup_docs` (on success)
- Extend `_telemetry_used_lookup()` in `usage.py` to treat recent events
  (default: rolling 7-day window, aligned with loop metrics) as satisfied
  lookups for SessionStart / disk-only gap reports.

**Effect:** CLI warmup clears SessionStart hints and stop-hook gap followups
without requiring a redundant MCP call.

### Out of scope (this ADR)

- Changing the `lookup_docs_underused` ratio gap semantics (still MCP/hook biased).
- Recording failed lookups or brain-only doc paths in the events file.
- Auto-generating AGENTS.md / skill copy (follow-up docs pass).

## Consequences

**Positive**

- Fewer false-positive pipeline gaps when docs are already on disk.
- CLI/MCP parity for compliance telemetry without duplicate Context7 fetches.
- SessionStart `usage-gaps-hint` reflects CLI warmup from prior sessions.

**Negative / tradeoffs**

- `find_uncached_libraries()` calls `cache.list_entries()` once per gap
  computation (acceptable; gap tools are not hot-path).
- Fuzzy cache match at 0.85 may occasionally treat a typo import as cached;
  threshold chosen conservatively (exact + alias first).

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| MCP-only: document "always call tapps_lookup_docs via MCP" | Does not fix CLI parity or yaml/pyyaml false positives |
| Suppress gap whenever any cache dir exists | Too coarse; ignores which libraries edits reference |
| Write CLI events into `loop-metrics.jsonl` | Overloads Stop-hook schema; mixed semantics |
| Expand `LIBRARY_ALIASES` only in fuzzy_matcher | Lookup path already fuzzy; gap check bypassed import_analyzer |

## Implementation checklist

- [x] ADR-0021 (this document)
- [x] `tapps_core.knowledge.import_analyzer`: `is_library_cached`, alias map, tests
- [x] `tapps_mcp.tools.lookup_telemetry`: append/read JSONL, tests
- [x] `tapps_mcp.tools.usage`: `_telemetry_used_lookup` reads events
- [x] `tapps_mcp.cli` + `server.tapps_lookup_docs`: record on success
- [x] `test_usage_gaps_hint`: yaml/pyyaml + CLI telemetry cases
- [ ] AGENTS.md / finish-task skill copy (follow-up docs pass)
