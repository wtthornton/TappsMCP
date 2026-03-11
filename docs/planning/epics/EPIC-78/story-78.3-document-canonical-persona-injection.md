# Story 78.3: Document canonical persona injection as prompt-injection defense

**Epic:** [EPIC-78-CANONICAL-PERSONA-INJECTION-PROMPT-INJECTION-DEFENSE](../EPIC-78-CANONICAL-PERSONA-INJECTION-PROMPT-INJECTION-DEFENSE.md)  
**Priority:** P2 | **LOE:** 0.5 day

## Problem

Users and integrators should understand that canonical persona injection is a prompt-injection mitigation (inject trusted persona content so the model’s definition of “who” is fixed by the project). Without a short doc section, the feature may be underused or misunderstood.

## Purpose & Intent

This story exists so that **users and integrators understand canonical persona injection as a security feature**. Documenting it in AGENTS.md or a dedicated doc ensures the mitigation is discoverable and correctly applied, and links the implementation to the research rationale so future changes stay aligned with the intent.

## Tasks

- [ ] Add a short section **“Canonical persona injection”** or **“Persona injection (prompt-injection mitigation)”** in one of: `AGENTS.md` (project root), `docs/` (e.g. security or pipeline doc), or a dedicated `docs/SECURITY.md` / `docs/PROMPT_INJECTION_MITIGATION.md`. Prefer AGENTS.md “When to use” for the tool plus a pointer to a fuller explanation, or a subsection under “Essential tools” / “Security.”
- [ ] Section content: (1) When the user requests a persona by name, the agent can call `tapps_get_canonical_persona` to retrieve the **trusted** definition from project (or user) agent/rule files; (2) prepending that content and treating it as the only valid definition mitigates persona override and prompt-injection attempts that try to redefine the persona in the user message; (3) link to `docs/planning/research/2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md` §7 for full rationale.
- [ ] Ensure the research doc §7 is linked from this section.

## Acceptance criteria

- [ ] Documentation explains that canonical persona injection is used to mitigate persona override / prompt injection.
- [ ] Research doc §7 is linked; readers can find the full design and rationale.

## Files

- `AGENTS.md` and/or `docs/TAPPS_MCP_SETUP_AND_USE.md` or new `docs/PROMPT_INJECTION_MITIGATION.md` (choose one primary; cross-link if needed)
- No code changes; research doc is existing.

## Dependencies

- Story 78.1 (tool) and 78.2 (rule) should be in place so the doc describes a live feature.

## References

- Epic 78; docs/planning/research/2026-AGENTS-RESEARCH-CLAUDE-CURSOR-AGENCY-AGENTS.md §7
