# Story 93.7 -- Dependency Audit and Updates

<!-- docsmcp:start:user-story -->

> **As a** security-conscious maintainer, **I want** every dependency with a known CVE upgraded and every unused dependency removed, **so that** TappsMCP does not transitively ship vulnerabilities into downstream projects.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 2 | **Size:** XS

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

Dependency drift is silent: a package that was clean last quarter may ship a CVE today. This story runs the scan, applies minimum-patched upgrades, and trims unused deps.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Run `tapps_dependency_scan` on each package. For each dep with a known CVE, upgrade to the minimum version that patches the CVE (avoid gratuitous major bumps). Remove any dep flagged as unused. Re-evaluate the tapps-brain pin (`v2.0.3`) against the latest upstream release; if a newer compatible version exists, bump it.

Run the full test suite after upgrades to confirm no breakage.

See [Epic 93](../EPIC-93-full-code-review-and-fixes.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/tapps-core/pyproject.toml`
- `packages/tapps-mcp/pyproject.toml`
- `packages/docs-mcp/pyproject.toml`
- `uv.lock`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Run `tapps_dependency_scan` on each package; capture reports
- [ ] Upgrade every dep with a known CVE to minimum patched version
- [ ] Remove every dep flagged as unused
- [ ] Re-evaluate tapps-brain pin against upstream
- [ ] Run `uv sync --all-packages` and regenerate lock
- [ ] Run full test suite; fix any breakage from upgrades

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `tapps_dependency_scan` reports zero known CVEs across all packages
- [ ] No unused dependencies remain in any pyproject.toml
- [ ] tapps-brain pin documented as current-or-intentionally-pinned
- [ ] Full test suite passes after upgrades
- [ ] `uv.lock` committed

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
