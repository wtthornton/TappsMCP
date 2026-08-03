# 33. Pin tapps-brain version floor at 3.28.0 (range: >=3.28.0, <4)

Date: 2026-08-03

## Status

Accepted (supersedes the 3.24.0 floor in [ADR-0013](0013-pin-tapps-brain-version-floor-at-3240.md), which itself superseded the 3.18.0 floor in [ADR-0010](0010-pin-tapps-brain-version-floor-at-3180.md)). The workspace source pin remains tag-based per [ADR-0011](0011-pin-tapps-brain-by-tag.md).

## Context

[ADR-0030](0030-unified-research-entry-point-brain-backed-cache.md) moved `tapps_research`
onto brain-owned web research so provider credentials (Exa / Tavily / Firecrawl) stay
brain-side. The consumer binding (TAP-5365) landed in `HttpBrainBridge.web_research()` and
`HttpBrainBridge.research_fetch()`, which call the brain MCP tools of the same names.

Those two tools **ship in tapps-brain 3.28.0** — they did not exist in 3.24.x–3.27.x. The
runtime floor was never raised to match, so `check_brain_version` accepted brains as old as
3.24.0 while `tapps_research` unconditionally called a tool they do not expose. The failure
surfaced at invocation time as an unknown-tool / out-of-profile error rather than at session
start, where the version probe exists precisely to catch this class of mismatch. The
`tapps_research` remediation text already told operators to run "brain ≥ 3.28.0"; the
enforced floor disagreed with it.

Two secondary facts settled at the same time:

- `v3.28.1` is now tagged upstream. The workspace comment claiming it was an untagged master
  build was stale, and the live brain service already runs 3.28.1.
- The pre-push guard's `_REQUIRED_BRAIN_FLOOR` was still `3.18.0`, two floors behind what
  CLAUDE.md documented, so it would not have caught a regression below 3.24.0 either.

## Decision

Raise the floor to **3.28.0** in four places, atomically:

1. `packages/tapps-core/pyproject.toml`: `tapps-brain>=3.28.0,<4`
2. `packages/tapps-core/src/tapps_core/brain_bridge.py`: `_BRAIN_VERSION_FLOOR = "3.28.0"`
3. `.githooks/pre-push`: `_REQUIRED_BRAIN_FLOOR="3.28.0"`
4. Workspace `pyproject.toml` `[tool.uv.sources]`: `tag = "v3.28.1"`

The source pin (3.28.1) sits one patch above the floor (3.28.0) deliberately: the floor is the
minimum capability tapps-mcp requires of *any* brain it talks to, while the source pin tracks
the version this repo builds and deploys against. 3.28.1 adds no API tapps-mcp binds — it
scopes brain-side idempotency keys by operation — so it is not floor-worthy.

## Consequences

- Consumers running brain 3.24.x–3.27.x now fail `brain_bridge.version_check` at session
  start with an actionable message, instead of getting a working memory surface and a broken
  `tapps_research`.
- The version probe and the `tapps_research` remediation text agree for the first time.
- The pre-push guard actually enforces the documented floor.
- In-process and HTTP transports continue to share one floor.

## Alternatives considered

- **Leave the floor at 3.24.0 and let `tapps_research` degrade.** Rejected: the degraded path
  is an unknown-tool error at call time, which reads to an agent as a transient brain fault
  rather than "your brain is too old." A version floor whose purpose is catching capability
  mismatch should catch this one.
- **Feature-probe `tools/list` for `web_research` instead of a version floor.** The bridge
  already caches `tools/list` for profile negotiation, so this is technically available.
  Rejected as the primary mechanism: it reports "tool absent" identically for "brain too old"
  and "tool gated out of this profile," which need different operator actions. The version
  floor separates them. Profile gating stays the job of `ToolNotInProfileError`.
- **Raise the floor to 3.28.1 to match the source pin.** Rejected: nothing tapps-mcp calls
  requires 3.28.1, and an unnecessarily high floor forces consumer upgrades that buy them
  nothing.

## Refs

- [ADR-0011](0011-pin-tapps-brain-by-tag.md) — pin by release tag
- [ADR-0013](0013-pin-tapps-brain-version-floor-at-3240.md) — superseded floor
- [ADR-0030](0030-unified-research-entry-point-brain-backed-cache.md) — brain-backed research
- Linear: TAP-5364 (brain), TAP-5365 (consumer binding)
