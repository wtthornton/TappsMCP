# 10. Pin tapps-brain version floor at 3.18.0 (range: >=3.18.0, <4)

Date: 2026-05-16

## Status

accepted (supersedes [ADR-0009](0009-pin-tapps-brain-version-floor-at-3170.md); historical chain: [ADR-0002](0002-pin-tapps-brain-version-floor-at-372.md) → ADR-0009 → ADR-0010)

## Context

tapps-brain 3.18.0 closed the deprecation window opened in 3.17.0 and **removed** two MCP tool aliases:

- `memory_recall(message=...)` — callers must now pass `query=` (the canonical kwarg shared with `memory_search` and `brain_recall`).
- `brain_learn_success(task_description=...)` — callers must now pass `description=` (the canonical kwarg shared with `brain_learn_failure`).

The companion Python client wrappers (`TappsBrainClient.memory_recall`, `TappsBrainClient.learn_success`, and their async variants) were renamed to `query` / `description` in the same release. Positional callers are unaffected; keyword callers on the deprecated names will raise `TypeError` against a 3.18.0 brain.

The 3.17.0 floor declared by [ADR-0009](0009-pin-tapps-brain-version-floor-at-3170.md) no longer reflects what tapps-mcp safely consumes at runtime: a 3.17.x brain accepts the dependency install but the cross-repo bridge code is now expected to use the canonical kwargs. The bridge already does — `packages/tapps-core/src/tapps_core/brain_bridge.py` passes `query=` and `description=` — so the bump is forward-only with no callsite migration.

Beyond the alias removal, 3.18.0 also lands operator-visible improvements that tapps-mcp benefits from passively:

- `/v1/tools/list` static-snapshot route + p95/p99 cold-path benchmark gate (TAP-1843, TAP-1855).
- `tapps_brain_mcp_probe_duration_seconds` Prometheus histogram on `/metrics` (TAP-1849) — surfaced via the `brain_bridge_health` probe in `tapps_session_start`.
- DB-checked `/healthz` and tightened compose healthcheck (TAP-1835).
- Migration rollback CLI + paired `*.down.sql` invariant (TAP-1818).
- `AsyncMemoryStore` thread-pool semaphore guards (TAP-1815).

The `_BRAIN_VERSION_FLOOR` constant in `packages/tapps-core/src/tapps_core/brain_bridge.py` (used by the runtime version probe and `tapps doctor`) was lagging the pyproject pin for the same reason ADR-0009 flagged: keeping the two values in sync is load-bearing — if the constant lags the resolver pin, `tapps_session_start` accepts a brain that the dependency resolver would have rejected, and the failure surfaces only when a 3.18-only contract is invoked.

## Decision

Raise the floor to **3.18.0** in three places, atomically:

1. `packages/tapps-core/pyproject.toml`: `tapps-brain>=3.17.0,<4` → `tapps-brain>=3.18.0,<4`
2. `packages/tapps-core/src/tapps_core/brain_bridge.py`: `_BRAIN_VERSION_FLOOR = "3.17.0"` → `"3.18.0"`
3. Workspace `pyproject.toml` `[tool.uv.sources]` Git rev: `a3654693…` (v3.8.0) → `afb9fbe05f8befe0544399f9d824e891059a566f` (v3.18.0)

The constant comment in `brain_bridge.py` (`Keep in sync with the tapps-brain pin in packages/tapps-core/pyproject.toml`) is unchanged but remains load-bearing — future bumps must move both the pyproject pin and the constant in the same commit. The ceiling stays `<4`. No other package's pyproject pins tapps-brain directly.

## Consequences

**Positive:**

- The dependency resolver refuses to install a tapps-brain that no longer accepts the deprecated alias kwargs, so callsites that still rely on `message=` / `task_description=` fail at install rather than at call time.
- The runtime version probe (`brain_bridge_health` in `tapps_session_start`) reports an actionable error against any brain older than 3.18.0, matching what the resolver already enforces.
- The workspace Git rev now matches the pyproject floor — local dev and CI resolve the same artifact as a fresh consumer install, eliminating a stale-rev foot-gun that lasted from v3.8.0 through 3.17.x.
- Passive uptake of the 3.18.0 operator-observability surface (`/v1/tools/list` static snapshot, probe-latency histogram, DB-checked `/healthz`).

**Negative:**

- Consumers of `tapps-core` who pinned tapps-brain in the 3.7.x–3.17.x range must upgrade to install. This is the explicit purpose of the bump.
- Any external caller still passing `memory_recall(message=...)` or `brain_learn_success(task_description=...)` against the bumped brain will get a `TypeError`. The bridge does not use these aliases; consumers outside this repo may.

**Neutral:**

- `tapps_memory` actions that pre-date the 3.17 → 3.18 alias removal continue to work — the bridge already migrated to canonical kwargs as part of the 3.17.0 floor in ADR-0009.
- The runtime BrainBridge code (`HttpBrainBridge`, `BrainBridge` base) is unchanged. Only the floor declarations move.

## Alternatives considered

**Leave the floor at 3.17.0 and accept that the deprecation aliases are gone but unused.** Rejected: ADR-0009 documents the atomic-bump invariant — pyproject pin and `_BRAIN_VERSION_FLOOR` must agree. The whole point of the runtime probe is to surface drift at session start, not at call time. The probe reports `3.18.0` from the running brain; leaving the floor at 3.17.0 silently accepts brains that the project no longer tests against.

**Loosen the upper bound to `<5` in the same commit.** Rejected: out of scope. The `<4` ceiling reflects an unknown major boundary and should be revisited as its own ADR if and when 4.0 ships.

**Switch the Git rev to a tag (`tag = "v3.18.0"`) instead of a SHA.** Rejected for now: tag-based resolution is racier under uv's lockfile semantics than an immutable commit SHA. The comment in `[tool.uv.sources]` already records the path to swap to a tag once the upstream release tags are durable; this ADR keeps the SHA pin for resolver determinism.
