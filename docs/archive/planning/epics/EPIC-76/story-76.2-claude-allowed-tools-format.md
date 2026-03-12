# Story 76.2: Claude allowed-tools: space-delimited for spec

**Epic:** [EPIC-76-SKILLS-SPEC-COMPLIANCE-AND-VALIDATION](../EPIC-76-SKILLS-SPEC-COMPLIANCE-AND-VALIDATION.md)  
**Priority:** P2 | **LOE:** 1–2 days

## Problem

The Agent Skills spec says `allowed-tools` is a space-delimited list. TappsMCP Claude skills use comma-separated values (e.g. `allowed-tools: mcp__tapps-mcp__tapps_score_file, mcp__tapps-mcp__tapps_quick_check`). For spec compliance we should switch to space-delimited unless Claude Code requires commas.

## Purpose & Intent

This story exists so that **Claude skills are spec-compliant and portable** across the Agent Skills ecosystem. Aligning with the standard allowed-tools format reduces the risk of breakage when Claude or other clients tighten spec enforcement and keeps our output interchangeable with other spec-compliant skills.

## Tasks

- [ ] Change CLAUDE_SKILLS in platform_skills.py so every `allowed-tools` value is space-delimited (e.g. `mcp__tapps-mcp__tapps_score_file mcp__tapps-mcp__tapps_quick_check`). Use YAML quoted string or multi-line if needed for readability.
- [ ] Run manual check (or existing integration test) that Claude Code still restricts tools when a skill is invoked; if not, revert and document “Claude Code requires comma-separated” in the research doc.
- [ ] Update test_platform_skills.py if it asserts on comma presence; assert space-delimited or “list of tools” presence instead.
- [ ] Add a one-line comment in platform_skills.py or research doc: “allowed-tools is space-delimited per agentskills.io spec.”

## Acceptance criteria

- [ ] Claude skill frontmatter uses space-delimited allowed-tools.
- [ ] Claude Code behavior unchanged (tool allowlist still applied) or documented exception.
- [ ] Tests updated and passing.

## Files

- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py`
- `packages/tapps-mcp/tests/unit/test_platform_skills.py`
- `docs/planning/research/2026-SKILLS-RESEARCH-TAPPSMCP.md`

## References

- agentskills.io (allowed-tools space-delimited); Epic 76; CLAUDE_SKILLS dict
