# Brain v3.18.0 Kwarg Audit — TAP-1977

**Date:** 2026-05-23  
**Status:** ✅ Migration already complete — zero offenders found  
**Auditor:** TAP-1977 review

## Background

Brain v3.18.0 (2026-05-16) removed two kwargs:

| Old kwarg | New kwarg | Tool |
|---|---|---|
| `memory_recall(message=...)` | `memory_recall(query=...)` | `memory_recall` |
| `brain_learn_success(task_description=...)` | `brain_learn_success(description=...)` | `brain_learn_success` |

A naive pin bump to `>=3.18.0` would raise `TypeError` at runtime if any call site still passed the old kwargs.

## Audit Results

### Scope

```
rg "memory_recall(message=" packages/ --include="*.py"
rg "brain_learn_success(task_description=" packages/ --include="*.py"
```

Search ran across:
- `packages/tapps-core/src/` — BrainBridge HTTP client wrapper
- `packages/tapps-mcp/src/` — MCP tool dispatch surface
- `packages/tapps-mcp/tests/` — unit and integration test fixtures
- `packages/tapps-core/tests/` — bridge-level test fixtures
- `packages/docs-mcp/src/` — docs-mcp integration layer

### `memory_recall(message=...)` — **0 occurrences**

No files pass `message=` to `memory_recall`. The BrainBridge already uses
`query=` canonically (see `brain_bridge.py` line 1647: `_http_mcp_call("memory_recall", args)`
where args is `{"query": ...}`).

### `brain_learn_success(task_description=...)` — **0 occurrences**

No files pass `task_description=` to `brain_learn_success`. The bridge uses
`description=` everywhere.

## Conclusion

Both rewrite stories (TAP-1978, TAP-1979) are already done — the bridge was
migrated before these tasks were filed. No further code changes are required.

TAP-1978 and TAP-1979 can be closed as **Done — pre-existing migration confirmed by this audit**.

## References

1. ADR-0010 (`docs/adr/0010-pin-tapps-brain-version-floor-at-3180.md`) — confirms bridge does not use deprecated aliases
2. Brain `CHANGELOG.md` v3.18.0 — kwarg removal entries
3. `packages/tapps-core/src/tapps_core/brain_bridge.py` — current implementation
