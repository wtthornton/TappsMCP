# Story 93.8 -- Documentation Drift Repair

<!-- docsmcp:start:user-story -->

> **As a** new contributor or consuming project, **I want** AGENTS.md, README.md, and CLAUDE.md to accurately reflect the current MCP tool inventory and behavior, **so that** I do not waste time chasing stale instructions or missing tools.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 2 | **Size:** XS

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

Documentation drifts with every feature shipped. This story is the final pass of Epic 93: reconcile docs with the code that prior stories fixed.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Run `docs_check_drift` on each package. Enumerate every `@mcp.tool()` decorator across tapps-mcp and docs-mcp and compare the resulting tool list against AGENTS.md. Update tool counts, parameter signatures, and examples that drifted. Sync the README.md claims (tool count, coverage numbers) with reality. Verify the "Known gotchas" section in CLAUDE.md still applies after the fixes from 93.2/93.4/93.5.

See [Epic 93](../EPIC-93-full-code-review-and-fixes.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `AGENTS.md`
- `README.md`
- `CLAUDE.md`
- `docs/ARCHITECTURE.md`
- `packages/*/README.md` (if any)

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Run `docs_check_drift` on each package
- [ ] Enumerate `@mcp.tool()` handlers; diff against AGENTS.md
- [ ] Update tool counts, parameter lists, examples
- [ ] Sync README.md tool-count and coverage claims with reality
- [ ] Verify CLAUDE.md "Known gotchas" still applies; remove stale entries
- [ ] Run `docs_check_links` to confirm no broken links introduced

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `docs_check_drift` reports zero drift per package
- [ ] AGENTS.md tool list matches `@mcp.tool()` inventory exactly
- [ ] README.md tool counts and coverage numbers are current
- [ ] CLAUDE.md "Known gotchas" contains no stale entries
- [ ] `docs_check_links` passes with zero broken links

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] docs_check_drift and docs_check_links pass clean
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
