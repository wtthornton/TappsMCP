# 13. Pin tapps-brain version floor at 3.24.0 (range: >=3.24.0, <4)

Date: 2026-06-09

## Status

Accepted (supersedes the 3.18.0 floor in [ADR-0010](0010-pin-tapps-brain-version-floor-at-3180.md); workspace source pin remains rev-based until `v3.24.0` tag ships — see [ADR-0011](0011-pin-tapps-brain-by-tag.md). Amended by [ADR-0015](0015-require-tapps-brain-docs-lookup-at-3240.md) for `docs_lookup` / `docs_warm` capability when `docs_via_brain` is enabled.)

## Context

TAP-1997 phase 2 migrates metrics dashboard reads from interim `memory_save` keys to
`brain_query_events`, which ships in tapps-brain **3.24.0**. Phase 1.5 dual-write landed
in tapps-mcp 3.12.12; the HTTP brain at `localhost:8080` already reports 3.24.0 and
`bridge.query_events("quality_metric")` round-trips cleanly.

The `v3.24.0` Git tag is not published yet; main HEAD (`0a3e173…`) carries version
3.24.0. Until the tag exists, the workspace `[tool.uv.sources]` entry uses that rev;
`uv.lock` retains commit-level determinism per ADR-0011.

## Decision

Raise the floor to **3.24.0** in three places, atomically:

1. `packages/tapps-core/pyproject.toml`: `tapps-brain>=3.24.0,<4`
2. `packages/tapps-core/src/tapps_core/brain_bridge.py`: `_BRAIN_VERSION_FLOOR = "3.24.0"`
3. Workspace `pyproject.toml` `[tool.uv.sources]`: rev `0a3e173181d4b3179244add93e5fb18ce1336fc5` (3.24.0 pre-tag)

Switch the source pin to `tag = "v3.24.0"` when the release tag is published.

## Consequences

- `load_tool_call_metrics_from_brain()` reads `brain_query_events` payloads; interim
  `metrics:tool_call:*` memory keys are no longer written on emit.
- Consumers on brain `<3.24.0` see `brain_bridge.version_check` errors until upgraded.
- In-process and HTTP transports share the same floor.

## Alternatives considered

- **Stay at 3.18.0 floor** — leaves version probe accepting brains that lack
  `brain_query_events`; dashboard `TAPPS_METRICS_STORAGE=brain` would silently return
  empty history.
- **Floor 3.23.0** — latest published tag; does not include `brain_query_events`.
