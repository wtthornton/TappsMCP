# Story 70.1 — Define personas for remaining 15 built-in experts

<!-- docsmcp:start:user-story -->
> **As a** TappMCP maintainer, **I want** every built-in expert to have a short, stance-aware persona, **so that** consultation answers have a consistent identity and default stance per domain.
<!-- docsmcp:end:user-story -->

<!-- docsmcp:start:sizing -->
**Points:** 2 | **Size:** S
<!-- docsmcp:end:sizing -->

## Description

Add or extend `persona` for all 15 built-in experts that do not yet have one (Performance, Testing, Code Quality, DevOps, Data Privacy, Accessibility, UX, Documentation, AI Frameworks, Agent Learning, Observability, API Design, Cloud, Database, GitHub). Security and Software Architecture already have personas from Epic 69. Keep each persona to 1–3 sentences: role + default stance.

## Tasks

- [ ] Add or extend `persona` for all 15 experts in `packages/tapps-core/src/tapps_core/experts/registry.py`
- [ ] Keep each persona to 1–3 sentences; no markdown or code
- [ ] Update or add unit tests that assert persona presence for all 17 experts

## Acceptance Criteria

- [ ] All 17 entries in `BUILTIN_EXPERTS` have non-empty `persona`
- [ ] Personas are concise and domain-appropriate
- [ ] Tests pass; no change to ExpertConfig schema

## Definition of Done

- [ ] Registry updated and tests pass
- [ ] No regression in consultation behavior
