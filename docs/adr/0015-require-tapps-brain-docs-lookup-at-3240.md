# 15. Require tapps-brain docs_lookup at 3.24.0+ (ADR-0014 consumer floor)

Date: 2026-06-13

## Status

Accepted (amends [0013](0013-pin-tapps-brain-version-floor-at-3240.md); implements
[0014](0014-brain-central-doc-rag-big-bang.md) version-floor item)

## Context

ADR-0013 pins `tapps-brain>=3.24.0,<4` for `brain_query_events` (TAP-1997). ADR-0014
adds brain-central library doc RAG (`docs_lookup`, `docs_warm`, `docs import-dir`) on
the same 3.24.0 release train (tapps-brain `ac6c474`). Consumers enabling
`docs_via_brain` must not negotiate against a brain that lacks those tools.

## Decision

1. **Version range unchanged:** `tapps-brain>=3.24.0,<4` in `packages/tapps-core/pyproject.toml`
   and `_BRAIN_VERSION_FLOOR = "3.24.0"` in `brain_bridge.py`.
2. **Workspace source pin** at tapps-brain `d893fc1cbf0df77112c29fdd321e690068c0985f`
   (`docs_lookup`, `docs_warm`, `docs import-dir`; TAP-3865/3866). Switch to
   `tag = "v3.24.0"` when the release tag includes this commit.
3. **Capability expectation:** when `docs_via_brain` is enabled, operators must run brain
   3.24.0+ with `docs_lookup` / `docs_warm` on the `full` profile. `tapps-mcp doctor`
   gates legacy disk caches and consumer Context7 env keys post-cutover.
4. **Consumer flag:** `TAPPS_MCP_DOCS_VIA_BRAIN=1` or `docs_via_brain: true` in
   `.tapps-mcp.yaml` (opt-in until fleet cutover completes).

## Consequences

- ADR-0013 remains the numeric floor; this ADR adds the docs-tool capability requirement
  for cutover consumers.
- Brains at 3.24.0 without the docs commit fail `docs_lookup` calls; tapps-core falls
  back to local KBCache only when the tool is absent (pre-cutover grace).
- Fleet cutover runbook documents the maintenance window.

## Alternatives considered

- **Bump floor to 3.25.0** — unnecessary; docs ship on the 3.24.0 train.
- **Hard-fail version probe on missing docs_lookup** — too brittle for mixed fleets
  during the maintenance window; doctor + opt-in flag suffice.
