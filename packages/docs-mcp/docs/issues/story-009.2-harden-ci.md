# Story 9.2 -- Harden CI Pipeline

<!-- docsmcp:start:user-story -->

> **As a** server administrator, **I want** CI pipeline improvements including coverage thresholds, security scanning, and TAPPS quality gates on direct pushes, **so that** quality regressions and security issues are caught before code reaches main

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 3 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that the CI pipeline catches quality regressions, enforces minimum coverage, and runs security scanning on every PR — preventing issues from reaching main.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Add coverage enforcement, expand TAPPS quality gate triggers, and add security scanning to CI. Commit uv.lock for reproducible builds.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `.github/workflows/ci.yml`
- `.github/workflows/tapps-quality.yml`
- `uv.lock`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Add --cov-fail-under=80 to pytest step in ci.yml (`.github/workflows/ci.yml`)
- [ ] Commit uv.lock to repo (`uv.lock`)
- [ ] Add push trigger to tapps-quality.yml (`.github/workflows/tapps-quality.yml`)
- [ ] Add bandit/pip-audit security step to ci.yml (`.github/workflows/ci.yml`)
- [ ] Verify all jobs pass on a test PR

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] pytest --cov-fail-under=80 enforced in CI
- [ ] uv.lock committed and used for frozen installs
- [ ] TAPPS quality gate runs on push to main (not just PRs)
- [ ] Security scanning (bandit or pip-audit) runs in CI
- [ ] All existing tests continue to pass

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Harden CI Pipeline code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] Documentation updated
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
