# Story 71.1 — Add critical_rules / default_stance field to ExpertConfig and business config

<!-- docsmcp:start:user-story -->
> **As a** TappMCP maintainer, **I want** ExpertConfig to support an optional critical rules or default stance field, **so that** experts can enforce domain-appropriate constraints in consultation answers.
<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 2 | **Size:** S
<!-- docsmcp:end:sizing -->

## Description

Add optional field (e.g. `critical_rules: str = ""` or `default_stance: str = ""`) to ExpertConfig and business expert config. Document the field; ensure backward compatibility and unit tests for config with and without the field.

## Tasks

- [ ] Add optional `critical_rules` or `default_stance` to `tapps_core/experts/models.py` (ExpertConfig)
- [ ] Update `tapps_core/experts/business_config.py` if it mirrors ExpertConfig
- [ ] Add unit tests for config with and without the field
- [ ] Document field in model docstring and in knowledge README or EXPERT_CONFIG_GUIDE

## Acceptance Criteria

- [ ] ExpertConfig and business expert entry support the new optional field; default empty
- [ ] Existing experts unchanged; tests pass

## Definition of Done

- [ ] Schema updated, backward compatible, tests pass
