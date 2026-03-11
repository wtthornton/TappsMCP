# Epic 76: Skills Spec Compliance & Validation

<!-- docsmcp:start:metadata -->
- **Status:** Complete (2026-03-11)
- **Priority:** P2
- **Estimated LOE:** ~1.5–2 weeks (1 developer)
- **Dependencies:** Epic 36 (Hook & Platform Expansion — skills), agentskills.io specification
- **Blocks:** None
- **Source:** docs/planning/research/2026-SKILLS-RESEARCH-TAPPSMCP.md
<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:goal -->
## Goal

Align TappsMCP-generated skills (`.claude/skills/`, `.cursor/skills/`) with the Agent Skills specification (agentskills.io) and add validation so that description length, allowed-tools format, and frontmatter rules are enforced. Resolve Cursor `mcp_tools` vs standard `allowed-tools` and Claude comma vs space-delimited allowed-tools.
<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

1. **Spec compliance:** The open SKILL.md spec requires `name` (max 64 chars, match dir) and `description` (1–1024 chars). Optional `allowed-tools` is space-delimited. TappsMCP uses comma-separated allowed-tools for Claude and `mcp_tools` (YAML list) for Cursor; description length is unchecked.
2. **Portability:** Skills that follow the spec work across 27+ agents. Fixing format and adding validation reduces drift and supports future Cursor/Claude behavior changes.
3. **Quality:** A validator (e.g. in tests or CLI) catches regressions when skill templates are edited.
<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that **TappsMCP-generated skills are spec-compliant and portable** across the Agent Skills ecosystem (27+ agents and growing). Skills that violate the agentskills.io spec—description length, allowed-tools format, or frontmatter rules—risk breaking in future Cursor/Claude versions or in other clients that strictly enforce the spec. By enforcing description length, aligning allowed-tools format (space-delimited where the spec says so), and documenting or validating Cursor’s mcp_tools vs standard allowed-tools, we future-proof our generated artifacts and give consumers confidence that TappsMCP output works everywhere. The intent is to reduce drift, support portability, and catch regressions early so that skills remain a reliable, standards-based surface for tool guidance.
<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria (Epic-level)

- [ ] Every generated skill’s `description` is ≤1024 characters; test or validator enforces this.
- [ ] Claude skills use space-delimited `allowed-tools` (or comma is documented as a Claude extension and validated); no regression in Claude Code behavior.
- [ ] Cursor skills: either use standard `allowed-tools` (space-delimited) for portability, or retain `mcp_tools` with documented rationale and validation that Cursor still applies tool restrictions.
- [ ] Optional: a small validator (pytest helper or `tapps-mcp validate-skills`) that checks frontmatter (name, description length, name regex, dir match) and optionally allowed-tools format.
- [ ] All 11 Claude and 11 Cursor skills pass the new validation; existing skill tests pass.
<!-- docsmcp:end:acceptance-criteria -->

---

<!-- docsmcp:start:stories -->
## Stories

| Story | Title | Priority | LOE |
|-------|--------|----------|-----|
| [76.1](EPIC-76/story-76.1-description-length-validation.md) | Description length validation (≤1024 chars) | P2 | 1 day |
| [76.2](EPIC-76/story-76.2-claude-allowed-tools-format.md) | Claude allowed-tools: space-delimited for spec | P2 | 1–2 days |
| [76.3](EPIC-76/story-76.3-cursor-allowed-tools-vs-mcp-tools.md) | Cursor: allowed-tools vs mcp_tools decision | P2 | 1 day |
| [76.4](EPIC-76/story-76.4-skills-spec-validator.md) | Optional skills spec validator (test or CLI) | P3 | 1–2 days |

<!-- docsmcp:end:stories -->

## Implementation notes

| Item | Location |
|------|----------|
| Skill templates (Claude) | `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py` — dict `CLAUDE_SKILLS` |
| Skill templates (Cursor) | Same file — dict `CURSOR_SKILLS` |
| Generate skills | `generate_skills()` in platform_skills.py (or platform_generators); called from init/upgrade |
| Tests | `packages/tapps-mcp/tests/unit/test_platform_skills.py` |
| Validator (76.4) | New function in platform_skills.py or `packages/tapps-mcp/src/tapps_mcp/pipeline/skills_validator.py` |
| CLI (76.4 optional) | `packages/tapps-mcp/src/tapps_mcp/cli.py` — add `validate-skills` command |

**Story order:** 76.1 first (description length); 76.2 and 76.3 can be parallel; 76.4 depends on 76.1 (validator reuses description check).

## References

- **Research:** docs/planning/research/2026-SKILLS-RESEARCH-TAPPSMCP.md
- **Spec:** https://agentskills.io/specification
- **Code:** packages/tapps-mcp/src/tapps_mcp/pipeline/platform_skills.py, test_platform_skills.py
