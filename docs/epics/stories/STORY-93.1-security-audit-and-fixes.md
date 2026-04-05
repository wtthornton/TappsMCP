# Story 93.1 -- Security Audit and Fixes

<!-- docsmcp:start:user-story -->

> **As a** maintainer of TappsMCP, **I want** every security finding across the monorepo triaged and fixed, **so that** downstream consumers can trust that the quality tooling they depend on does not itself ship exploitable code.

<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 5 | **Size:** M

<!-- docsmcp:end:sizing -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

This story exists so that a baseline security audit runs against all three packages and every HIGH/MEDIUM finding is fixed before we layer on more features. File writes and subprocess calls must all flow through the established `security/path_validator.py` and `security/command_runner.py` gates.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:description -->
## Description

Run `bandit -r packages/tapps-core/src packages/tapps-mcp/src packages/docs-mcp/src` and capture the baseline. Triage each finding; fix HIGH and MEDIUM severity issues. Separately, grep for raw `open(`, `Path.write_text`, `Path.write_bytes`, `subprocess.run`, `subprocess.Popen`, `os.system`, `os.popen` across `src/` and verify each call site either goes through the path validator / command runner or has a documented reason why it cannot.

Also verify `structlog` redaction is configured so tokens, API keys, and filesystem paths that contain `.ssh` or `.aws` are scrubbed from log output.

See [Epic 93](../EPIC-93-full-code-review-and-fixes.md) for project context and shared definitions.

<!-- docsmcp:end:description -->

<!-- docsmcp:start:files -->
## Files

- `packages/tapps-core/src/tapps_core/security/path_validator.py`
- `packages/tapps-core/src/tapps_core/security/command_runner.py`
- `packages/tapps-core/src/tapps_core/logging/*.py`
- `packages/*/src/**/*.py` (fix sites)
- `packages/*/tests/unit/test_security_*.py`

<!-- docsmcp:end:files -->

<!-- docsmcp:start:tasks -->
## Tasks

- [ ] Run `bandit -r packages/*/src/` and commit the baseline report under `docs/archive/`
- [ ] Triage each finding (HIGH, MEDIUM, LOW); file LOW findings as follow-ups
- [ ] Fix every HIGH and MEDIUM finding
- [ ] Grep for `open(`, `write_text`, `write_bytes`, `subprocess`, `os.system`, `os.popen` in `src/`
- [ ] Route any unprotected call through `path_validator` / `command_runner`
- [ ] Verify structlog processors redact tokens, API keys, and sensitive paths
- [ ] Add regression tests for each security fix
- [ ] Re-run `bandit` and confirm zero HIGH/MEDIUM findings remain

<!-- docsmcp:end:tasks -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] `bandit -r packages/*/src/` reports zero HIGH or MEDIUM findings
- [ ] Every `open`/`write_text`/`subprocess` call site is either validated or documented
- [ ] structlog redaction covers tokens, API keys, and SSH/AWS credential paths
- [ ] Each fixed finding has a regression test
- [ ] Baseline bandit report archived under `docs/archive/`

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:definition-of-done -->
## Definition of Done

- [ ] All tasks completed
- [ ] Code reviewed and approved
- [ ] Tests passing (unit + integration)
- [ ] bandit scan passes clean
- [ ] No regressions introduced

<!-- docsmcp:end:definition-of-done -->
