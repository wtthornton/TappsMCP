# Story 76.1: Description length validation (≤1024 chars)

**Epic:** [EPIC-76-SKILLS-SPEC-COMPLIANCE-AND-VALIDATION](../EPIC-76-SKILLS-SPEC-COMPLIANCE-AND-VALIDATION.md)  
**Priority:** P2 | **LOE:** 1 day

## Problem

The Agent Skills spec requires `description` to be 1–1024 characters. TappsMCP skill templates use multi-line descriptions (`>-`) and have no check; a future edit could exceed 1024 characters and break spec-compliant clients.

## Purpose & Intent

This story exists so that **every generated skill stays within the Agent Skills spec** and we catch regressions in CI. Enforcing the 1–1024 character description range future-proofs our skills for any client that strictly follows agentskills.io and prevents accidental breakage when descriptions are expanded.

## Tasks

- [ ] Add a test in `test_platform_skills.py` (or equivalent) that, for every skill in CLAUDE_SKILLS and CURSOR_SKILLS, parses the frontmatter, extracts the `description` value (after YAML join/fold), and asserts `1 <= len(description) <= 1024`.
- [ ] If any current description exceeds 1024 characters, shorten it (preserve “what and when to use” and keywords) so the test passes.
- [ ] Document in 2026-SKILLS-RESEARCH-TAPPSMCP.md that description length is enforced.

## Acceptance criteria

- [ ] All 11 Claude and 11 Cursor skills have description length ≤1024 characters.
- [ ] A test asserts this for both CLAUDE_SKILLS and CURSOR_SKILLS; test runs in CI.
- [ ] Research doc updated.

## Files

- `packages/tapps-mcp/tests/unit/test_platform_skills.py`
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py` (only if trimming descriptions)
- `docs/planning/research/2026-SKILLS-RESEARCH-TAPPSMCP.md`

## References

- agentskills.io specification (description 1–1024 chars); Epic 76; platform_skills.CLAUDE_SKILLS, CURSOR_SKILLS
