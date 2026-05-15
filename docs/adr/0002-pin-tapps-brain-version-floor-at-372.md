# 2. Pin tapps-brain version floor at 3.7.2 (range: >=3.7.2, <4)

Date: 2026-05-02

## Status

superseded by [ADR-0009](0009-pin-tapps-brain-version-floor-at-3170.md)

## Context

tapps-mcp consumes tapps-brain through `BrainBridge` (in-process; see ADR-0001) — but the `tapps-core` package still declares `tapps-brain` as a Python dependency. The version range affects future migrations to remote brain-as-a-service: when tapps-mcp eventually swaps `BrainBridge` for `TappsBrainClient`, that client must work. tapps-brain 3.7.0 and 3.7.1 had two known defects: a wrong `/mcp` vs `/mcp/mcp` path in `TappsBrainClient`, and a streamable-HTTP lifespan crash. Both were fixed in 3.7.2.

## Decision

`packages/tapps-core/pyproject.toml` pins `tapps-brain >= 3.7.2, < 4`. The floor is bumped despite tapps-mcp not currently exercising `TappsBrainClient` (it uses `AgentBrain` via `BrainBridge`), because: (a) any future migration to remote brain inherits a working client, (b) the cost of the floor bump is zero for current in-process callers, and (c) it removes a known foot-gun for any sibling project that picks up `tapps-core` and does use the HTTP client. Imports remain wrapped in `try/except ImportError` for defensive degradation in non-standard installs.

## Consequences

**Positive:** Future remote-brain migration is unblocked from the dependency side. Sibling projects using `tapps-core` get the fixed `TappsBrainClient` automatically.

**Negative:** Consumers of `tapps-core` who pinned an older tapps-brain must upgrade to install.

**Neutral:** No runtime change for tapps-mcp itself.
