# 9. Pin tapps-brain version floor at 3.17.0 (range: >=3.17.0, <4)

Date: 2026-05-15

## Status

superseded by [ADR-0010](0010-pin-tapps-brain-version-floor-at-3180.md) (originally supersedes [ADR-0002](0002-pin-tapps-brain-version-floor-at-372.md))

## Context

After TAP-1628 shipped, `tapps_memory` now routes nine new actions — `recall_many`, `reinforce_many`, `rate`, `related`, `relations`, `neighbors`, `explain_connection`, `search_sessions`, and `session_end` — through brain-native MCP tools that only exist in tapps-brain 3.17.0 and later. The floor declared by [ADR-0002](0002-pin-tapps-brain-version-floor-at-372.md) (`>=3.7.2`) no longer matches what tapps-mcp actually requires at runtime: a 3.7.2 brain accepts the dependency install but raises `BrainBridgeUnavailable` (or returns a degraded payload) the moment a caller hits any of the new actions.

The `_BRAIN_VERSION_FLOOR` constant in `packages/tapps-core/src/tapps_core/brain_bridge.py` (used by the runtime version probe and `tapps doctor`) was lagging the pyproject pin for the same reason. Keeping the two values in sync is load-bearing — if the constant lags the resolver pin, `tapps_session_start` accepts a brain that the dependency resolver would have rejected, and the failure surfaces only when a 3.17-only action is invoked.

## Decision

Raise the floor to **3.17.0** in two places, atomically:

1. `packages/tapps-core/pyproject.toml`: `tapps-brain>=3.7.2,<4` → `tapps-brain>=3.17.0,<4`
2. `packages/tapps-core/src/tapps_core/brain_bridge.py`: `_BRAIN_VERSION_FLOOR = "3.7.2"` → `"3.17.0"`

The constant comment in `brain_bridge.py` (`Keep in sync with the tapps-brain pin in packages/tapps-core/pyproject.toml`) is unchanged but now load-bearing — future bumps must move both values in the same commit.

The ceiling stays `<4`. No other package's pyproject pins tapps-brain directly.

## Consequences

**Positive:**

- The pin matches what tapps-mcp actually requires. Consumers can no longer install a tapps-brain that would silently fail at the new action surface.
- The runtime version probe (`brain_bridge_health` in `tapps_session_start`) reports an actionable error against any brain older than 3.17.0, instead of letting the failure surface at action-call time.
- The atomic-bump invariant is documented as a load-bearing rule rather than an implicit convention.

**Negative:**

- Consumers of `tapps-core` who pinned tapps-brain in the 3.7.x–3.16.x range must upgrade to install. This is the explicit purpose of the bump; the older brains lack the surface tapps-mcp uses.

**Neutral:**

- `tapps_memory` actions that pre-date TAP-1628 continue to work — the bump is forward-only.
- The runtime BrainBridge code (`HttpBrainBridge`, `BrainBridge` base) is unchanged. Only the floor declaration moves.

## Alternatives considered

**Leave the floor at 3.7.2 and gate each new action on a runtime probe.** Rejected: doubles the failure path (resolver allows install, action raises `BrainBridgeUnavailable`), and `tapps doctor` cannot pre-flight the mismatch. The whole reason `_BRAIN_VERSION_FLOOR` exists is to surface this kind of drift at session start, not at action-call time.

**Loosen the upper bound to `<5` in the same commit.** Rejected: out of scope. The `<4` ceiling reflects an unknown major boundary and should be revisited as its own ADR if and when 4.0 ships.
