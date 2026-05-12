# 8. Delete SQLite MemoryPersistence edge-case tests

Status: Accepted
Date: 2026-05-04
Linear: TAP-1375

## Context

`packages/tapps-mcp/tests/unit/test_memory_epic23_integration.py::TestPersistenceEdgeCases`
exercised the local SQLite-backed `MemoryPersistence` class — schema-version
pinning at v17, FTS5 special-character handling, and empty-query behavior.

That class was removed from this repo in commit `f5f4132` (EPIC-95.1+95.2)
when persistence moved to tapps-brain v3 (see ADR-0001, ADR-0002, and the
sibling tapps-brain repo's ADR-0007). `tapps_mcp.memory.persistence` is now a thin re-export
shim aliasing `tapps_brain.store.MemoryStore`. The shim has a different
constructor signature, schema versioning scheme (returns `1`, not `17`), and
`save()` API (`save(key, value, ...)` not `save(MemoryEntry)`), so the
edge-case tests fail when re-enabled — they assert behavior of code that
no longer lives in this repo.

The tests had been muted with `@pytest.mark.skip` since `f5f4132`, creating
a silent coverage gap surfaced by TAP-1375.

## Decision

Delete `TestPersistenceEdgeCases` outright. Equivalent coverage is owned by
the tapps-brain test suite (schema versioning, FTS, edge cases on empty
input), which is the source of truth per ADR-0001.

## Consequences

- One fewer skip-with-explanation in tapps-mcp's test suite.
- If a future regression in tapps-brain breaks the shim, it surfaces in
  tapps-brain CI, not here. That's correct given the repository boundary.
