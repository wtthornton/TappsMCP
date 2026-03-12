# Story 76.3: Cursor: allowed-tools vs mcp_tools decision

**Epic:** [EPIC-76-SKILLS-SPEC-COMPLIANCE-AND-VALIDATION](../EPIC-76-SKILLS-SPEC-COMPLIANCE-AND-VALIDATION.md)  
**Priority:** P2 | **LOE:** 1 day

## Problem

The Agent Skills spec defines optional `allowed-tools` (space-delimited). Cursor’s public docs do not mention `allowed-tools` or `mcp_tools`. TappsMCP uses `mcp_tools:` (YAML list) for Cursor. We need a documented decision: use standard `allowed-tools` for Cursor (if supported) or keep `mcp_tools` with a clear rationale.

## Purpose & Intent

This story exists so that **Cursor skills are either spec-aligned or explicitly documented as a Cursor extension**. A clear, tested decision (allowed-tools vs mcp_tools) prevents guesswork and ensures we maintain Cursor tool restriction behavior while documenting any divergence from the open spec for future maintainers and users.

## Tasks

- [ ] Verify Cursor behavior: if possible, test a Cursor skill with `allowed-tools: tapps_score_file tapps_quick_check` (space-delimited) and confirm the agent still restricts to those tools when the skill is active. If Cursor ignores it, try `mcp_tools` and confirm it is applied.
- [ ] Decision: (A) If Cursor respects `allowed-tools`, add `allowed-tools` to CURSOR_SKILLS (space-delimited, short tool names as currently used in body) and optionally keep `mcp_tools` for backward compatibility until Cursor docs clarify. (B) If Cursor only respects `mcp_tools`, keep `mcp_tools` and add a short “Cursor extension” note in the research doc and a code comment in platform_skills.py.
- [ ] Update 2026-SKILLS-RESEARCH-TAPPSMCP.md with the outcome and recommendation.
- [ ] If we add `allowed-tools` for Cursor, update test_platform_skills.py so Cursor skills are allowed to have either or both; avoid breaking existing “Cursor uses mcp_tools” assertion if we keep both.

## Acceptance criteria

- [ ] Decision is documented (use allowed-tools for Cursor vs keep mcp_tools).
- [ ] CURSOR_SKILLS either include spec-compliant `allowed-tools` or retain `mcp_tools` with documented rationale.
- [ ] Tests remain green; research doc updated.

## Files

- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py`
- `packages/tapps-mcp/tests/unit/test_platform_skills.py`
- `docs/planning/research/2026-SKILLS-RESEARCH-TAPPSMCP.md`

## References

- Cursor docs (skills/subagents); agentskills.io; Epic 76; CURSOR_SKILLS dict
