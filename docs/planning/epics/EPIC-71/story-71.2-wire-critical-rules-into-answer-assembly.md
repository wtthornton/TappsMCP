# Story 71.2 — Wire critical rules into consultation answer assembly

<!-- docsmcp:start:user-story -->
> **As a** user of tapps_consult_expert, **I want** the expert's critical rules or default stance to be included in the answer prompt when set, **so that** responses follow domain-appropriate constraints.
<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 2 | **Size:** M
<!-- docsmcp:end:sizing -->

## Description

In `tapps_core/experts/engine.py`, after persona preamble, if expert has non-empty critical_rules/default_stance, append a "Critical rules" or "Default stance" block to the prompt text used for answer assembly. Add unit tests for persona only, persona + rules, rules only, neither.

## Tasks

- [ ] In _build_answer, after persona, prepend rules when set (e.g. "You must follow: {rules}")
- [ ] Keep total preamble concise; document max length in docs
- [ ] Add unit tests: expert with persona only, persona + rules, rules only, neither
- [ ] Ensure ConsultationResult/answer metadata unchanged (rules are prompt-only)

## Acceptance Criteria

- [ ] When critical_rules/default_stance is set, it appears in assembly prompt after persona
- [ ] When empty, behavior unchanged
- [ ] Tests cover all combinations; no regression in output schema

## Definition of Done

- [ ] Engine updated, tests pass
