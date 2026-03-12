# Story 71.3 — Add pilot critical rules for Security, Testing, and Accessibility experts

<!-- docsmcp:start:user-story -->
> **As a** consumer of tapps_consult_expert, **I want** Security, Testing, and Accessibility experts to apply explicit default stances, **so that** answers are consistently cautious and actionable.
<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 1 | **Size:** S
<!-- docsmcp:end:sizing -->

## Description

Add non-empty critical_rules (or default_stance) in registry for Security, Testing, and Accessibility. Examples: Security — "Assume an attacker; require explicit justification for any exception to secure-by-default." Testing — "Prefer explicit tests over implicit behavior; never approve untested critical paths; default to recommending coverage." Accessibility — "WCAG 2.1 AA as baseline; assume diverse abilities and assistive technology; recommend testing with real assistive tech." Update docs with examples and guidance.

## Tasks

- [ ] Set critical_rules for Security, Testing, and Accessibility in `registry.py`
- [ ] Keep each rule to 1–2 sentences; no markdown
- [ ] Update knowledge README or EXPERT_CONFIG_GUIDE with examples and guidance on writing rules

## Acceptance Criteria

- [ ] At least these three experts have non-empty critical_rules in BUILTIN_EXPERTS
- [ ] Documentation updated; tests pass

## Definition of Done

- [ ] Registry and docs updated, tests pass
